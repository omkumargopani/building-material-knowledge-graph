import argparse
import csv
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase
from rdflib import Graph, Literal, Namespace, RDF, URIRef
from rdflib.namespace import XSD
from pyshacl import validate

ROOT = Path(__file__).resolve().parents[1]
EX = Namespace("https://example.org/building-kg/")


def read_rows(filename):
    with (ROOT / "data" / filename).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [{key: value.strip() for key, value in row.items()} for row in rows]


def load_data():
    data = {
        "buildings": read_rows("buildings.csv"),
        "components": read_rows("components.csv"),
        "materials": read_rows("materials.csv"),
        "findings": read_rows("findings.csv"),
    }
    for key, identifier in [
        ("buildings", "building_id"),
        ("components", "component_id"),
        ("materials", "material_id"),
        ("findings", "finding_id"),
    ]:
        values = [row[identifier] for row in data[key]]
        if len(values) != len(set(values)) or not all(values):
            raise ValueError(f"Duplicate or empty identifiers in {key}")
    buildings = {row["building_id"] for row in data["buildings"]}
    materials = {row["material_id"] for row in data["materials"]}
    components = {row["component_id"] for row in data["components"]}
    for row in data["components"]:
        if row["building_id"] not in buildings or row["material_id"] not in materials:
            raise ValueError(f"Invalid component references: {row['component_id']}")
    for row in data["findings"]:
        if row["component_id"] not in components:
            raise ValueError(f"Invalid finding component: {row['finding_id']}")
        if not row["substance_id"] or not row["report_id"] or not row["substance_name"] or not row["report_title"]:
            raise ValueError(f"Missing finding field: {row['finding_id']}")
        if not row["source_page"].isdigit() or int(row["source_page"]) < 1:
            raise ValueError(f"Invalid source page: {row['finding_id']}")
    return data


def build_rdf(data):
    graph = Graph()
    graph.bind("ex", EX)
    def add_resource(kind, identifier, rdf_type, name=None):
        resource = EX[f"{kind}/{identifier}"]
        graph.add((resource, RDF.type, rdf_type))
        graph.add((resource, EX.identifier, Literal(identifier, datatype=XSD.string)))
        if name is not None:
            graph.add((resource, EX.name, Literal(name, datatype=XSD.string)))
        return resource
    for row in data["buildings"]:
        add_resource("building", row["building_id"], EX.Building, row["name"])
    for row in data["materials"]:
        add_resource("material", row["material_id"], EX.Material, row["name"])
    for row in data["components"]:
        node = add_resource("component", row["component_id"], EX.Component, row["name"])
        graph.add((node, EX.partOf, EX[f"building/{row['building_id']}"]))
        graph.add((node, EX.madeOf, EX[f"material/{row['material_id']}"]))
    for row in data["findings"]:
        node = add_resource("finding", row["finding_id"], EX.Finding)
        substance = add_resource("substance", row["substance_id"], EX.Substance, row["substance_name"])
        document = add_resource("report", row["report_id"], EX.SourceDocument, row["report_title"])
        graph.add((node, EX.aboutComponent, EX[f"component/{row['component_id']}"]))
        graph.add((node, EX.reportsSubstance, substance))
        graph.add((node, EX.supportedBy, document))
        graph.add((node, EX.sourcePage, Literal(int(row["source_page"]), datatype=XSD.integer)))
    return graph


def validate_rdf(graph):
    shapes = Graph().parse(ROOT / "shapes" / "buildings.ttl", format="turtle")
    conforms, _, report = validate(graph, shacl_graph=shapes, inference="rdfs", abort_on_first=False)
    if not conforms:
        raise ValueError(str(report))
    return str(report)


def load_neo4j(data):
    load_dotenv(ROOT / ".env")
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "localpassword123")
    database = os.getenv("NEO4J_DATABASE", "neo4j")
    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        driver.verify_connectivity()
        for label in ["Building", "Component", "Material", "Substance", "Finding", "SourceDocument"]:
            driver.execute_query(
                f"CREATE CONSTRAINT {label.lower()}_id IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE",
                database_=database,
            )
        queries = [
            ("UNWIND $rows AS row MERGE (b:Building {id: row.building_id}) SET b.name = row.name, b.city = row.city", data["buildings"]),
            ("UNWIND $rows AS row MERGE (m:Material {id: row.material_id}) SET m.name = row.name, m.category = row.category, m.density_kg_m3 = toFloat(row.density_kg_m3)", data["materials"]),
            ("UNWIND $rows AS row MATCH (b:Building {id: row.building_id}) MATCH (m:Material {id: row.material_id}) MERGE (c:Component {id: row.component_id}) SET c.name = row.name, c.location = row.location MERGE (b)-[:HAS_COMPONENT]->(c) MERGE (c)-[:MADE_OF]->(m)", data["components"]),
            ("UNWIND $rows AS row MATCH (c:Component {id: row.component_id}) MERGE (s:Substance {id: row.substance_id}) SET s.name = row.substance_name MERGE (d:SourceDocument {id: row.report_id}) SET d.title = row.report_title MERGE (f:Finding {id: row.finding_id}) SET f.source_page = toInteger(row.source_page), f.status = row.status MERGE (c)-[:HAS_FINDING]->(f) MERGE (f)-[:REPORTS_SUBSTANCE]->(s) MERGE (f)-[:SUPPORTED_BY]->(d)", data["findings"]),
        ]
        for query, rows in queries:
            driver.execute_query(query, rows=rows, database_=database)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    data = load_data()
    rdf = build_rdf(data)
    output = ROOT / "data" / "building_graph.ttl"
    rdf.serialize(destination=output, format="turtle")
    print(f"Generated {len(rdf)} RDF triples at {output}")
    print(validate_rdf(rdf))
    if not args.validate_only:
        load_neo4j(data)
        print("Neo4j ingestion completed")


if __name__ == "__main__":
    main()
