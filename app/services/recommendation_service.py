from app.repositories.sku_repository import SKURepository
from app.services.distributor_service import DistributorService
from app.services.helpers.load_new_products_service import LoadNewProductsService
from app.services.helpers.sku_recommendation_service import SKURecommendationService


class RecommendationService:
    def __init__(self) -> None:
        self.distributor_service = DistributorService()
        self.sku_repository = SKURepository()
        self.graph_recommendation_service = SKURecommendationService()
        self.new_products_service = LoadNewProductsService()

    def get_sku_recommendations(self, distributor_code: str) -> dict:
        distributor = self.distributor_service.get_distributor_context(distributor_code)
        distributor_id = str(distributor["distributor_id"])
        profile_rows = self.sku_repository.get_distributor_recommendation_profile(
            distributor_code=distributor_code,
            distributor_id=distributor_id,
        )

        preferred_categories = self._get_preferred_categories(profile_rows)
        strong_sku_rows = self._get_strong_sku_rows(profile_rows)
        strong_sku_ids = [row["sku_id"] for row in strong_sku_rows]
        excluded_sku_ids = [row["sku_id"] for row in profile_rows if self._has_sales_signal(row)]

        recommendations_by_code = self._index_candidates(
            self._build_proven_candidates(profile_rows, distributor, preferred_categories)
        )
        self._merge_candidates(
            recommendations_by_code,
            self._get_graph_recommendations(
                distributor=distributor,
                strong_sku_ids=strong_sku_ids,
                preferred_categories=preferred_categories,
                exclude_sku_ids=excluded_sku_ids,
            ),
        )
        self._merge_candidates(
            recommendations_by_code,
            self._get_new_product_candidates(
                distributor=distributor,
                preferred_categories=preferred_categories,
                strong_sku_rows=strong_sku_rows,
                existing_sku_codes=set(recommendations_by_code.keys()),
            ),
        )

        recommendations = self._select_final_recommendations(recommendations_by_code)
        return {
            "distributor_code": distributor["distributor_code"],
            "distributor_name": distributor["name"],
            "recommended_skus": recommendations,
        }

    def _build_proven_candidates(
        self,
        profile_rows: list[dict],
        distributor: dict,
        preferred_categories: list[str],
    ) -> list[dict]:
        if not profile_rows:
            return []

        max_sales_qty = max(float(row["total_sales_qty"] or 0) for row in profile_rows) or 1.0
        max_avg_qty = max(float(row["avg_sales_qty"] or 0) for row in profile_rows) or 1.0
        max_sales_cycles = max(float(row["sales_cycle_count"] or 0) for row in profile_rows) or 1.0
        max_confirmed_qty = max(float(row["confirmed_30d_total"] or 0) for row in profile_rows) or 1.0

        candidates = []
        for row in profile_rows:
            if not self._has_sales_signal(row) and not self._has_demand_signal(row):
                continue

            sales_strength = (
                0.6 * (float(row["total_sales_qty"] or 0) / max_sales_qty)
                + 0.25 * (float(row["avg_sales_qty"] or 0) / max_avg_qty)
                + 0.15 * (float(row["sales_cycle_count"] or 0) / max_sales_cycles)
            )
            historical_sales_score = round(38 * sales_strength, 2)

            confirmation_rate = self._confirmation_rate(row)
            demand_strength = (
                0.7 * (float(row["confirmed_30d_total"] or 0) / max_confirmed_qty)
                + 0.3 * confirmation_rate
            )
            confirmed_demand_score = round(24 * demand_strength, 2)
            missed_confirmation_cycles = max(
                int(row["suggested_cycle_count"] or 0) - int(row["confirmed_cycle_count"] or 0),
                0,
            )
            confirmed_demand_score -= min(missed_confirmation_cycles * 2, 8)

            score_components = {
                "historical_sales_score": historical_sales_score,
                "confirmed_demand_score": confirmed_demand_score,
                "mapping_eligibility_score": 12.0 if row.get("is_mapped") else 0.0,
                "falkor_similarity_score": 0.0,
                "new_product_bonus": 0.0,
                "priority_bonus": self._priority_bonus(distributor.get("priority")),
                "category_affinity_bonus": 6.0 if row.get("category") in preferred_categories else 0.0,
            }
            final_score = int(round(sum(score_components.values())))

            reason_parts = []
            if historical_sales_score >= 20:
                reason_parts.append("High historical sales for this distributor")
            elif historical_sales_score > 0:
                reason_parts.append("Consistent historical sales for this distributor")

            if confirmed_demand_score >= 12:
                reason_parts.append("Previously confirmed in demand cycles")
            elif int(row["suggested_cycle_count"] or 0) > 0:
                reason_parts.append("Previously suggested and partially confirmed")

            if row.get("category") in preferred_categories:
                reason_parts.append("Strong fit with the distributor's preferred category")

            if distributor.get("priority") == "High":
                reason_parts.append("Boosted for high-priority distributor")

            candidates.append({
                "sku_id": str(row["sku_id"]),
                "sku_code": row["sku_code"],
                "sku_name": row["sku_name"],
                "category": row.get("category"),
                "score": final_score,
                "reason": "; ".join(reason_parts) or "Eligible proven product from distributor history",
                "source": "proven",
            })

        return candidates

    def _get_graph_recommendations(
        self,
        distributor: dict,
        strong_sku_ids: list[str],
        preferred_categories: list[str],
        exclude_sku_ids: list[str],
    ) -> list[dict]:
        distributor_id = str(distributor["distributor_id"])
        try:
            helper_response = self.graph_recommendation_service.execute(
                distributor_id=distributor_id,
                strong_sku_ids=strong_sku_ids,
                preferred_categories=preferred_categories,
                exclude_sku_ids=exclude_sku_ids,
                limit=8,
            )
        except Exception:
            return []

        raw_recommendations = helper_response.get("recommendations", [])
        if not raw_recommendations:
            return []

        sku_lookup = self.sku_repository.get_skus_by_ids(
            [item.get("sku_id") for item in raw_recommendations if item.get("sku_id")]
        )
        normalized_recommendations = []
        for item in raw_recommendations:
            normalized = self._normalize_graph_recommendation(
                item,
                distributor,
                preferred_categories,
                sku_lookup,
            )
            if normalized:
                normalized_recommendations.append(normalized)

        return normalized_recommendations

    def _normalize_graph_recommendation(
        self,
        recommendation: dict,
        distributor: dict,
        preferred_categories: list[str],
        sku_lookup: dict[str, dict],
    ) -> dict | None:
        sku_id = recommendation.get("sku_id")
        if sku_id is None:
            return None

        graph_score = recommendation.get("graph_score", recommendation.get("score", 0))
        try:
            raw_graph_score = float(graph_score)
        except (TypeError, ValueError):
            raw_graph_score = 0.0

        sku_id_str = str(sku_id)
        sku_record = sku_lookup.get(sku_id_str, {})
        category = sku_record.get("category") or recommendation.get("category")
        category_bonus = 4.0 if category in preferred_categories else 0.0
        score_components = {
            "historical_sales_score": 0.0,
            "confirmed_demand_score": 0.0,
            "mapping_eligibility_score": 0.0,
            "falkor_similarity_score": min(raw_graph_score * 4, 28.0),
            "new_product_bonus": 10.0 if recommendation.get("is_new_product") else 0.0,
            "priority_bonus": self._priority_bonus(distributor.get("priority")),
            "category_affinity_bonus": category_bonus,
        }
        final_score = int(round(sum(score_components.values())))

        reason_parts = ["Similar to top-performing SKU via FalkorDB"]
        if recommendation.get("is_new_product"):
            reason_parts.append("New launch linked to distributor purchase behavior")
        elif category in preferred_categories:
            reason_parts.append("Aligned with the distributor's preferred category")
        if distributor.get("priority") == "High":
            reason_parts.append("Boosted for high-priority distributor")

        sku_name = sku_record.get("sku_name") or recommendation.get("sku_name") or sku_id_str
        return {
            "sku_id": sku_id_str,
            "sku_code": sku_record.get("sku_code") or recommendation.get("sku_code") or sku_id_str,
            "sku_name": sku_name,
            "category": category,
            "score": final_score,
            "reason": "; ".join(reason_parts),
            "source": "new_product" if recommendation.get("is_new_product") else "graph_similar",
        }

    def _get_new_product_candidates(
        self,
        distributor: dict,
        preferred_categories: list[str],
        strong_sku_rows: list[dict],
        existing_sku_codes: set[str],
    ) -> list[dict]:
        try:
            new_products = self.new_products_service.execute()
        except Exception:
            return []

        strong_sku_ids = {str(row["sku_id"]).upper() for row in strong_sku_rows}
        strong_sku_names = {str(row["sku_name"]).upper() for row in strong_sku_rows}
        preferred_categories_set = {category for category in preferred_categories if category}
        candidates = []

        for _, row in new_products.iterrows():
            sku_id = str(row.get("SKU ID", "")).strip()
            sku_name = str(row.get("SKU Name", "")).strip()
            category = str(row.get("Category", "")).strip() or None
            similar_existing_sku = str(row.get("Similar to Existing SKU", "")).strip().upper()

            if not sku_id or sku_id in existing_sku_codes:
                continue

            category_match = category in preferred_categories_set if category else False
            similarity_match = (
                similar_existing_sku in strong_sku_ids
                or similar_existing_sku in strong_sku_names
            )
            if not category_match and not similarity_match:
                continue

            score_components = {
                "historical_sales_score": 0.0,
                "confirmed_demand_score": 0.0,
                "mapping_eligibility_score": 0.0,
                "falkor_similarity_score": 8.0 if similarity_match else 0.0,
                "new_product_bonus": 14.0,
                "priority_bonus": self._priority_bonus(distributor.get("priority")),
                "category_affinity_bonus": 8.0 if category_match else 0.0,
            }
            final_score = int(round(sum(score_components.values())))

            reason_parts = []
            if category_match:
                reason_parts.append("New product in the distributor's preferred category")
            if similarity_match:
                reason_parts.append("Linked to a strong existing SKU")
            if distributor.get("priority") == "High":
                reason_parts.append("Boosted for high-priority distributor")

            candidates.append({
                "sku_id": sku_id,
                "sku_code": sku_id,
                "sku_name": sku_name or sku_id,
                "category": category,
                "score": final_score,
                "reason": "; ".join(reason_parts) or "Relevant new product candidate",
                "source": "new_product",
            })

        return sorted(
            candidates,
            key=lambda item: (-item["score"], item["sku_code"]),
        )[:4]

    @staticmethod
    def _index_candidates(candidates: list[dict]) -> dict[str, dict]:
        return {
            candidate["sku_code"]: candidate
            for candidate in candidates
        }

    def _merge_candidates(self, target: dict[str, dict], candidates: list[dict]) -> None:
        for candidate in candidates:
            sku_code = candidate["sku_code"]
            existing = target.get(sku_code)
            if existing is None:
                target[sku_code] = candidate
                continue

            existing["score"] = max(existing["score"], candidate["score"])
            if candidate["reason"] not in existing["reason"]:
                existing["reason"] = f"{existing['reason']}; {candidate['reason']}"
            if not existing.get("category"):
                existing["category"] = candidate.get("category")
            existing["source"] = self._merge_source(existing.get("source"), candidate.get("source"))

    def _select_final_recommendations(self, recommendations_by_code: dict[str, dict]) -> list[dict]:
        all_candidates = sorted(
            recommendations_by_code.values(),
            key=lambda item: (-item["score"], item["sku_code"]),
        )

        selected: list[dict] = []
        selected_codes: set[str] = set()

        quotas = {
            "proven": 3,
            "graph_similar": 2,
            "new_product": 2,
        }
        for source, limit in quotas.items():
            count = 0
            for candidate in all_candidates:
                if len(selected) >= 5 or count >= limit:
                    break
                if candidate["sku_code"] in selected_codes or candidate.get("source") != source:
                    continue
                selected.append(candidate)
                selected_codes.add(candidate["sku_code"])
                count += 1

        for candidate in all_candidates:
            if len(selected) >= 5:
                break
            if candidate["sku_code"] in selected_codes:
                continue
            selected.append(candidate)
            selected_codes.add(candidate["sku_code"])

        return [
            {
                "sku_id": item["sku_id"],
                "sku_code": item["sku_code"],
                "sku_name": item["sku_name"],
                "category": item.get("category"),
                "score": int(item["score"]),
                "reason": item["reason"],
            }
            for item in selected[:5]
        ]

    @staticmethod
    def _get_preferred_categories(profile_rows: list[dict]) -> list[str]:
        category_scores: dict[str, float] = {}
        for row in profile_rows:
            category = row.get("category")
            if not category:
                continue
            category_scores.setdefault(category, 0.0)
            category_scores[category] += float(row["total_sales_qty"] or 0)
            category_scores[category] += float(row["confirmed_30d_total"] or 0) * 0.8
            category_scores[category] += float(row["sales_cycle_count"] or 0) * 5

        return [
            category
            for category, _ in sorted(
                category_scores.items(),
                key=lambda item: (-item[1], item[0]),
            )[:3]
        ]

    def _get_strong_sku_rows(self, profile_rows: list[dict]) -> list[dict]:
        return sorted(
            [row for row in profile_rows if self._has_sales_signal(row) or self._has_demand_signal(row)],
            key=lambda row: (
                -float(row["confirmed_30d_total"] or 0),
                -float(row["total_sales_qty"] or 0),
                row["sku_code"],
            ),
        )[:3]

    @staticmethod
    def _has_sales_signal(row: dict) -> bool:
        return float(row["total_sales_qty"] or 0) > 0 or int(row["sales_row_count"] or 0) > 0

    @staticmethod
    def _has_demand_signal(row: dict) -> bool:
        return float(row["confirmed_30d_total"] or 0) > 0 or int(row["suggested_cycle_count"] or 0) > 0

    @staticmethod
    def _confirmation_rate(row: dict) -> float:
        suggested_cycles = float(row["suggested_cycle_count"] or 0)
        if suggested_cycles <= 0:
            return 0.0
        return min(float(row["confirmed_cycle_count"] or 0) / suggested_cycles, 1.0)

    @staticmethod
    def _priority_bonus(priority: str | None) -> float:
        if priority == "High":
            return 8.0
        if priority == "Medium":
            return 5.0
        return 2.0

    @staticmethod
    def _merge_source(existing_source: str | None, new_source: str | None) -> str:
        if existing_source == "proven" or new_source == "proven":
            return "proven"
        if existing_source == "graph_similar" or new_source == "graph_similar":
            return "graph_similar"
        return new_source or existing_source or "proven"
