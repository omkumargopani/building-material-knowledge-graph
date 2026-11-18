import pytest
from rdflib import RDF

from src.pipeline import EX, build_rdf, load_data, validate_rdf


def test_valid_sample_data():
    graph = build_rdf(load_data())
    assert "Conforms: True" in validate_rdf(graph)


def test_missing_material_relation_fails_validation():
    graph = build_rdf(load_data())
    component = EX["component/W001"]
    for value in list(graph.objects(component, EX.madeOf)):
        graph.remove((component, EX.madeOf, value))
    with pytest.raises(ValueError):
        validate_rdf(graph)


def test_building_nodes_exist():
    graph = build_rdf(load_data())
    assert (EX["building/B001"], RDF.type, EX.Building) in graph
