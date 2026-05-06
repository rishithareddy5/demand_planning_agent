# =============================================================
# DEMAND PLANNING AGENT — FalkorDB Graph Schema + Seed
# File: db/falkordb/falkordb_seed.py
#
# Graph: demand_planning_graph
#
# Node types:
#   (:OEM)          — manufacturer (OEM01)
#   (:Distributor)  — 5 distributors (D01–D05)
#   (:SKU)          — 10 SKUs
#   (:Category)     — 4 product categories
#
# Edge types:
#   (:OEM)-[:MANUFACTURES]->(:SKU)
#   (:Distributor)-[:DISTRIBUTES]->(:SKU)      with priority, avg_dispatch_value
#   (:SKU)-[:BELONGS_TO]->(:Category)
#   (:Distributor)-[:SAME_TIER]->(:Distributor) between same-tier distributors
#
# Run:
#   docker exec -it demand_falkordb redis-cli ping   # verify FalkorDB is up
#   python db/falkordb/falkordb_seed.py
# =============================================================

import sys
import falkordb

# -----------------------------------------------------------
# CONNECTION
# -----------------------------------------------------------
FALKORDB_HOST = "localhost"
FALKORDB_PORT = 6379
GRAPH_NAME    = "demand_planning_graph"

def get_graph():
    client = falkordb.FalkorDB(host=FALKORDB_HOST, port=FALKORDB_PORT)
    return client.select_graph(GRAPH_NAME)

# -----------------------------------------------------------
# SEED DATA (from primary_sales_cleaned.xlsx)
# -----------------------------------------------------------

OEM = {
    "oem_id": "OEM01",
    "name": "OEM Manufacturer"
}

DISTRIBUTORS = [
    {"distributor_id": "D01", "name": "Distributor D01", "tier": "Tier 2", "channel": "Super Stockist",       "region": "Pan India", "priority": "Medium"},
    {"distributor_id": "D02", "name": "Distributor D02", "tier": "Tier 2", "channel": "Regional Distributor", "region": "Pan India", "priority": "Medium"},
    {"distributor_id": "D03", "name": "Distributor D03", "tier": "Tier 1", "channel": "Super Stockist",       "region": "Pan India", "priority": "High"},
    {"distributor_id": "D04", "name": "Distributor D04", "tier": "Tier 2", "channel": "Regional Distributor", "region": "Pan India", "priority": "Medium"},
    {"distributor_id": "D05", "name": "Distributor D05", "tier": "Tier 2", "channel": "Regional Distributor", "region": "Pan India", "priority": "Medium"},
]

SKUS = [
    {"sku_id": "SKU01", "name": "MALKIST CHEESE 48 PCS X 72",  "category": "MALKIST CHEESE",    "description": "MALKIST CHEESE 48 PCS X 72 GM-GT"},
    {"sku_id": "SKU02", "name": "MALKIST CHEESE G",             "category": "MALKIST CHEESE",    "description": "MALKIST CHEESE GB 16 X 30 X 18G"},
    {"sku_id": "SKU03", "name": "MALKIST CHEESE FAMILY 10",     "category": "MALKIST CHEESE",    "description": "MALKIST CHEESE FAMILY 10 X 6 X 144GM-GT"},
    {"sku_id": "SKU04", "name": "BENG BENG WAFER 22GM",         "category": "BENG BENG",         "description": "BENG BENG WAFER 12 X 25 X 22GM"},
    {"sku_id": "SKU05", "name": "BENG BENG WAFER GB",           "category": "BENG BENG",         "description": "BENG BENG WAFER GB 12 X 25 X 25G"},
    {"sku_id": "SKU06", "name": "KOPIKO CAPPU EXTRA",           "category": "KOPIKO CAPPUCCINO", "description": "KOPIKO CAPPU 12X230X3.5GR 15 PCS EXTRA"},
    {"sku_id": "SKU07", "name": "KOPIKO CAPPU + MALKIST",       "category": "KOPIKO CAPPUCCINO", "description": "KOPIKO CAPPU 4X650X3.5G+MALKIST 20PCS GB"},
    {"sku_id": "SKU08", "name": "KOPIKO CAPPUCCINO",            "category": "KOPIKO CAPPUCCINO", "description": "KOPIKO CAPPUCCINO 28 PCH X 120 X 3.5G"},
    {"sku_id": "SKU09", "name": "MALKIST SUGAR GB",             "category": "MALKIST SUGAR",     "description": "MALKIST SUGAR GB 16 X 30 X 18G"},
    {"sku_id": "SKU10", "name": "MALKIST SUGAR CRACKERS",       "category": "MALKIST SUGAR",     "description": "MALKIST SUGAR CRACKERS 10X 6 X 150G-RS50"},
]

CATEGORIES = ["MALKIST CHEESE", "BENG BENG", "KOPIKO CAPPUCCINO", "MALKIST SUGAR"]

# Distributor → SKU edges with priority and avg dispatch value
DISTRIBUTES = [
    # D01
    {"dist": "D01", "sku": "SKU01", "priority": "High",   "avg_dispatch": 119759.20},
    {"dist": "D01", "sku": "SKU02", "priority": "High",   "avg_dispatch": 122214.40},
    {"dist": "D01", "sku": "SKU03", "priority": "High",   "avg_dispatch": 458304.00},
    {"dist": "D01", "sku": "SKU04", "priority": "Medium", "avg_dispatch":  91660.80},
    {"dist": "D01", "sku": "SKU05", "priority": "Medium", "avg_dispatch": 109992.96},
    {"dist": "D01", "sku": "SKU06", "priority": "Medium", "avg_dispatch": 152768.00},
    {"dist": "D01", "sku": "SKU07", "priority": "Medium", "avg_dispatch":  91660.80},
    {"dist": "D01", "sku": "SKU08", "priority": "Low",    "avg_dispatch":  30553.60},
    {"dist": "D01", "sku": "SKU09", "priority": "Low",    "avg_dispatch": 235317.28},
    {"dist": "D01", "sku": "SKU10", "priority": "Low",    "avg_dispatch": 406676.60},
    # D02
    {"dist": "D02", "sku": "SKU01", "priority": "Medium", "avg_dispatch": 123032.80},
    {"dist": "D02", "sku": "SKU02", "priority": "Medium", "avg_dispatch": 123032.80},
    {"dist": "D02", "sku": "SKU03", "priority": "High",   "avg_dispatch": 461373.00},
    {"dist": "D02", "sku": "SKU04", "priority": "High",   "avg_dispatch":  91660.80},
    {"dist": "D02", "sku": "SKU05", "priority": "High",   "avg_dispatch": 110729.52},
    {"dist": "D02", "sku": "SKU06", "priority": "Medium", "avg_dispatch": 153791.00},
    {"dist": "D02", "sku": "SKU07", "priority": "Low",    "avg_dispatch":  92274.60},
    {"dist": "D02", "sku": "SKU08", "priority": "Low",    "avg_dispatch":  30758.20},
    {"dist": "D02", "sku": "SKU09", "priority": "Low",    "avg_dispatch": 235317.28},
    {"dist": "D02", "sku": "SKU10", "priority": "Medium", "avg_dispatch": 412159.88},
    # D03 (Tier 1 - all High)
    {"dist": "D03", "sku": "SKU01", "priority": "High",   "avg_dispatch": 119188.80},
    {"dist": "D03", "sku": "SKU02", "priority": "High",   "avg_dispatch": 120795.84},
    {"dist": "D03", "sku": "SKU03", "priority": "High",   "avg_dispatch": 452984.40},
    {"dist": "D03", "sku": "SKU04", "priority": "High",   "avg_dispatch":  90596.88},
    {"dist": "D03", "sku": "SKU05", "priority": "High",   "avg_dispatch": 108716.26},
    {"dist": "D03", "sku": "SKU06", "priority": "High",   "avg_dispatch": 150994.80},
    {"dist": "D03", "sku": "SKU07", "priority": "High",   "avg_dispatch":  90596.88},
    {"dist": "D03", "sku": "SKU08", "priority": "High",   "avg_dispatch":  30198.96},
    {"dist": "D03", "sku": "SKU09", "priority": "High",   "avg_dispatch": 229512.10},
    {"dist": "D03", "sku": "SKU10", "priority": "High",   "avg_dispatch": 407357.86},
    # D04
    {"dist": "D04", "sku": "SKU01", "priority": "Medium", "avg_dispatch": 123851.20},
    {"dist": "D04", "sku": "SKU02", "priority": "Medium", "avg_dispatch": 123851.20},
    {"dist": "D04", "sku": "SKU03", "priority": "Medium", "avg_dispatch": 464442.00},
    {"dist": "D04", "sku": "SKU04", "priority": "Low",    "avg_dispatch":  92888.40},
    {"dist": "D04", "sku": "SKU05", "priority": "Low",    "avg_dispatch": 111466.08},
    {"dist": "D04", "sku": "SKU06", "priority": "High",   "avg_dispatch": 152768.00},
    {"dist": "D04", "sku": "SKU07", "priority": "High",   "avg_dispatch":  92888.40},
    {"dist": "D04", "sku": "SKU08", "priority": "High",   "avg_dispatch":  30962.80},
    {"dist": "D04", "sku": "SKU09", "priority": "Low",    "avg_dispatch": 235317.28},
    {"dist": "D04", "sku": "SKU10", "priority": "Low",    "avg_dispatch": 417643.16},
    # D05
    {"dist": "D05", "sku": "SKU01", "priority": "Medium", "avg_dispatch": 124669.60},
    {"dist": "D05", "sku": "SKU02", "priority": "Medium", "avg_dispatch": 124669.60},
    {"dist": "D05", "sku": "SKU03", "priority": "Medium", "avg_dispatch": 470580.00},
    {"dist": "D05", "sku": "SKU04", "priority": "Medium", "avg_dispatch":  93502.20},
    {"dist": "D05", "sku": "SKU05", "priority": "Medium", "avg_dispatch": 112202.64},
    {"dist": "D05", "sku": "SKU06", "priority": "High",   "avg_dispatch": 153791.00},
    {"dist": "D05", "sku": "SKU07", "priority": "High",   "avg_dispatch":  93502.20},
    {"dist": "D05", "sku": "SKU08", "priority": "High",   "avg_dispatch":  31167.40},
    {"dist": "D05", "sku": "SKU09", "priority": "Low",    "avg_dispatch": 236872.24},
    {"dist": "D05", "sku": "SKU10", "priority": "Low",    "avg_dispatch": 417643.16},
]


# -----------------------------------------------------------
# SEED FUNCTIONS
# -----------------------------------------------------------

def drop_existing_graph(graph):
    try:
        graph.delete()
        print("✓ Dropped existing graph")
    except Exception:
        print("✓ No existing graph to drop")


def create_oem_node(graph):
    graph.query(
        "CREATE (:OEM {oem_id: $oem_id, name: $name})",
        {"oem_id": OEM["oem_id"], "name": OEM["name"]}
    )
    print(f"  ✓ OEM node: {OEM['oem_id']}")


def create_category_nodes(graph):
    for cat in CATEGORIES:
        graph.query(
            "CREATE (:Category {name: $name})",
            {"name": cat}
        )
    print(f"  ✓ Category nodes: {len(CATEGORIES)} created")


def create_distributor_nodes(graph):
    for d in DISTRIBUTORS:
        graph.query(
            """
            CREATE (:Distributor {
                distributor_id: $distributor_id,
                name:           $name,
                tier:           $tier,
                channel:        $channel,
                region:         $region,
                priority:       $priority
            })
            """,
            d
        )
    print(f"  ✓ Distributor nodes: {len(DISTRIBUTORS)} created")


def create_sku_nodes(graph):
    for s in SKUS:
        graph.query(
            """
            CREATE (:SKU {
                sku_id:      $sku_id,
                name:        $name,
                category:    $category,
                description: $description
            })
            """,
            s
        )
    print(f"  ✓ SKU nodes: {len(SKUS)} created")


def create_oem_manufactures_edges(graph):
    for s in SKUS:
        graph.query(
            """
            MATCH (o:OEM {oem_id: $oem_id}), (s:SKU {sku_id: $sku_id})
            CREATE (o)-[:MANUFACTURES]->(s)
            """,
            {"oem_id": OEM["oem_id"], "sku_id": s["sku_id"]}
        )
    print(f"  ✓ MANUFACTURES edges: {len(SKUS)} created")


def create_sku_belongs_to_edges(graph):
    for s in SKUS:
        graph.query(
            """
            MATCH (s:SKU {sku_id: $sku_id}), (c:Category {name: $category})
            CREATE (s)-[:BELONGS_TO]->(c)
            """,
            {"sku_id": s["sku_id"], "category": s["category"]}
        )
    print(f"  ✓ BELONGS_TO edges: {len(SKUS)} created")


def create_distributes_edges(graph):
    for edge in DISTRIBUTES:
        graph.query(
            """
            MATCH (d:Distributor {distributor_id: $dist}), (s:SKU {sku_id: $sku})
            CREATE (d)-[:DISTRIBUTES {
                priority:         $priority,
                avg_dispatch_value: $avg_dispatch
            }]->(s)
            """,
            edge
        )
    print(f"  ✓ DISTRIBUTES edges: {len(DISTRIBUTES)} created")


def create_same_tier_edges(graph):
    # Connect distributors in the same tier to each other
    tier2 = [d["distributor_id"] for d in DISTRIBUTORS if d["tier"] == "Tier 2"]
    count = 0
    for i in range(len(tier2)):
        for j in range(i + 1, len(tier2)):
            graph.query(
                """
                MATCH (a:Distributor {distributor_id: $a}), (b:Distributor {distributor_id: $b})
                CREATE (a)-[:SAME_TIER {tier: 'Tier 2'}]->(b)
                """,
                {"a": tier2[i], "b": tier2[j]}
            )
            count += 1
    print(f"  ✓ SAME_TIER edges: {count} created")


def verify_graph(graph):
    result = graph.query("MATCH (n) RETURN labels(n) AS label, count(n) AS count")
    print("\n=== GRAPH NODE COUNT ===")
    for row in result.result_set:
        print(f"  {row[0]}: {row[1]}")

    result2 = graph.query("MATCH ()-[r]->() RETURN type(r) AS rel, count(r) AS count")
    print("\n=== GRAPH EDGE COUNT ===")
    for row in result2.result_set:
        print(f"  {row[0]}: {row[1]}")


# -----------------------------------------------------------
# MAIN
# -----------------------------------------------------------
def main():
    print("Connecting to FalkorDB...")
    try:
        graph = get_graph()
        print("✓ Connected\n")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        sys.exit(1)

    print("Dropping existing graph...")
    drop_existing_graph(graph)

    print("\nCreating nodes...")
    create_oem_node(graph)
    create_category_nodes(graph)
    create_distributor_nodes(graph)
    create_sku_nodes(graph)

    print("\nCreating edges...")
    create_oem_manufactures_edges(graph)
    create_sku_belongs_to_edges(graph)
    create_distributes_edges(graph)
    create_same_tier_edges(graph)

    print("\nVerifying graph...")
    verify_graph(graph)

    print("\n✅ FalkorDB graph seeded successfully")


if __name__ == "__main__":
    main()