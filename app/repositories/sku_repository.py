from sqlalchemy import text
from app.core.database import SessionLocal


class SKURepository:
    def get_skus_for_distributor(self, distributor_code: str) -> list[dict]:
        query = text("""
            SELECT
                s.sku_id,
                s.sku_code,
                s.sku_name,
                s.category
            FROM skus s
            JOIN distributor_skus ds
              ON ds.sku_id = s.sku_id
            JOIN distributors d
              ON d.distributor_id = ds.distributor_id
            WHERE d.distributor_code = :distributor_code
              AND d.is_active = TRUE
              AND s.is_active = TRUE
              AND ds.is_active = TRUE
            ORDER BY s.sku_code
        """)

        with SessionLocal() as session:
            rows = session.execute(
                query,
                {"distributor_code": distributor_code}
            ).mappings().all()

            return [dict(row) for row in rows]

    def get_skus_by_ids(self, sku_ids: list[str]) -> dict[str, dict]:
        normalized_ids = [str(sku_id) for sku_id in sku_ids if sku_id is not None]
        if not normalized_ids:
            return {}

        query = text("""
            SELECT
                sku_id,
                sku_code,
                sku_name,
                category
            FROM skus
            WHERE CAST(sku_id AS TEXT) = ANY(:sku_ids)
              AND is_active = TRUE
        """)

        with SessionLocal() as session:
            rows = session.execute(
                query,
                {"sku_ids": normalized_ids}
            ).mappings().all()

        return {
            str(row["sku_id"]): dict(row)
            for row in rows
        }

    def get_distributor_recommendation_profile(
        self,
        distributor_code: str,
        distributor_id: str,
    ) -> list[dict]:
        query = text("""
            WITH mapped AS (
                SELECT
                    CAST(s.sku_id AS TEXT) AS sku_id,
                    s.sku_code,
                    s.sku_name,
                    s.category,
                    TRUE AS is_mapped
                FROM skus s
                JOIN distributor_skus ds
                  ON ds.sku_id = s.sku_id
                JOIN distributors d
                  ON d.distributor_id = ds.distributor_id
                WHERE d.distributor_code = :distributor_code
                  AND d.is_active = TRUE
                  AND s.is_active = TRUE
                  AND ds.is_active = TRUE
            ),
            sales AS (
                SELECT
                    CAST(ps.sku_id AS TEXT) AS sku_id,
                    COALESCE(SUM(ps.sales_qty), 0) AS total_sales_qty,
                    COALESCE(AVG(ps.sales_qty), 0) AS avg_sales_qty,
                    COUNT(ps.sale_id) AS sales_row_count,
                    COUNT(DISTINCT ps.cycle_id) AS sales_cycle_count,
                    MAX(ps.sale_date) AS last_sale_date
                FROM primary_sales ps
                WHERE ps.distributor_id = :distributor_id
                GROUP BY ps.sku_id
            ),
            demand AS (
                SELECT
                    CAST(dr.sku_id AS TEXT) AS sku_id,
                    COALESCE(SUM(dr.suggested_qty), 0) AS suggested_qty_total,
                    COALESCE(SUM(dr.confirmed_qty), 0) AS confirmed_qty_total,
                    COALESCE(SUM(COALESCE(dr.confirmed_30d_qty, dr.confirmed_qty, 0)), 0) AS confirmed_30d_total,
                    COUNT(dr.demand_id) AS suggested_cycle_count,
                    SUM(
                        CASE
                            WHEN COALESCE(dr.confirmed_30d_qty, dr.confirmed_qty, 0) > 0 THEN 1
                            ELSE 0
                        END
                    ) AS confirmed_cycle_count,
                    MAX(dc.cycle_date) AS last_confirmed_cycle
                FROM demand_records dr
                LEFT JOIN demand_cycles dc
                  ON dc.cycle_id = dr.cycle_id
                WHERE dr.distributor_id = :distributor_id
                GROUP BY dr.sku_id
            )
            SELECT
                mapped.sku_id,
                mapped.sku_code,
                mapped.sku_name,
                mapped.category,
                mapped.is_mapped,
                COALESCE(sales.total_sales_qty, 0) AS total_sales_qty,
                COALESCE(sales.avg_sales_qty, 0) AS avg_sales_qty,
                COALESCE(sales.sales_row_count, 0) AS sales_row_count,
                COALESCE(sales.sales_cycle_count, 0) AS sales_cycle_count,
                sales.last_sale_date,
                COALESCE(demand.suggested_qty_total, 0) AS suggested_qty_total,
                COALESCE(demand.confirmed_qty_total, 0) AS confirmed_qty_total,
                COALESCE(demand.confirmed_30d_total, 0) AS confirmed_30d_total,
                COALESCE(demand.suggested_cycle_count, 0) AS suggested_cycle_count,
                COALESCE(demand.confirmed_cycle_count, 0) AS confirmed_cycle_count,
                demand.last_confirmed_cycle
            FROM mapped
            LEFT JOIN sales
              ON sales.sku_id = mapped.sku_id
            LEFT JOIN demand
              ON demand.sku_id = mapped.sku_id
            ORDER BY mapped.sku_code
        """)

        with SessionLocal() as session:
            rows = session.execute(
                query,
                {
                    "distributor_code": distributor_code,
                    "distributor_id": distributor_id,
                },
            ).mappings().all()

        return [dict(row) for row in rows]
