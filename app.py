import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()
st.set_page_config(page_title="Building Material Explorer", page_icon="🏗️", layout="wide")
st.title("Building Material Knowledge Graph")
st.caption("Explore components, materials, reported substances, and source records. All bundled records are synthetic.")

@st.cache_resource
def get_driver():
    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "localpassword123")),
    )
    driver.verify_connectivity()
    return driver


def query(statement, **parameters):
    records, _, _ = get_driver().execute_query(
        statement,
        parameters_=parameters,
        database_=os.getenv("NEO4J_DATABASE", "neo4j"),
    )
    return [dict(record) for record in records]

try:
    buildings = query("MATCH (b:Building) RETURN b.id AS id, b.name AS name ORDER BY name")
except Exception as error:
    st.error(f"Cannot connect to Neo4j: {error}")
    st.info("Start Docker and run the ingestion command from README.md.")
    st.stop()

if not buildings:
    st.warning("No buildings found. Run the ingestion script first.")
    st.stop()

building_labels = {f"{b['name']} ({b['id']})": b["id"] for b in buildings}
selected_label = st.selectbox("Choose a building", list(building_labels))
building_id = building_labels[selected_label]

records = query(
    """
    MATCH (b:Building {id: $building_id})-[:HAS_COMPONENT]->(c:Component)-[:MADE_OF]->(m:Material)
    OPTIONAL MATCH (c)-[:HAS_FINDING]->(f:Finding)-[:REPORTS_SUBSTANCE]->(s:Substance)
    OPTIONAL MATCH (f)-[:SUPPORTED_BY]->(d:SourceDocument)
    RETURN c.id AS component_id, c.name AS component, c.location AS location,
           m.name AS material, m.category AS material_category,
           m.density_kg_m3 AS density_kg_m3,
           s.name AS reported_substance, f.status AS finding_status,
           d.title AS source_document, d.id AS report_id, f.source_page AS source_page
    ORDER BY c.id, s.name
    """,
    building_id=building_id,
)

left, middle, right = st.columns(3)
left.metric("Components", len({r["component_id"] for r in records}))
middle.metric("Materials", len({r["material"] for r in records}))
right.metric("Reported findings", sum(bool(r["reported_substance"]) for r in records))

show_hazards = st.checkbox("Show only components with reported substances", value=False)
filtered = [r for r in records if not show_hazards or r["reported_substance"]]
st.subheader("Inventory and source traceability")
st.dataframe(pd.DataFrame(filtered), use_container_width=True, hide_index=True)

st.subheader("Inspect a component")
component_options = {f"{r['component']} ({r['component_id']})": r["component_id"] for r in records}
selected_component = st.selectbox("Component", list(component_options))
selected_id = component_options[selected_component]
for record in records:
    if record["component_id"] == selected_id:
        with st.container(border=True):
            st.write(f"**Material:** {record['material']} · {record['material_category']}")
            st.write(f"**Location:** {record['location']}")
            if record["reported_substance"]:
                st.warning(f"Reported substance: {record['reported_substance']}")
                st.write(f"**Evidence:** {record['source_document']} ({record['report_id']}), page {record['source_page']}")
            else:
                st.info("No hazardous substance reported in the provided sample records. This is not a safety determination.")

st.caption("Source reports are illustrative metadata only; original report PDFs are not included.")
