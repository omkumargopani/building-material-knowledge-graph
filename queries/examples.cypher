MATCH (b:Building)-[:HAS_COMPONENT]->(c:Component)-[:MADE_OF]->(m:Material)
RETURN b.name AS building, c.name AS component, m.name AS material
ORDER BY building, component;

MATCH (b:Building)-[:HAS_COMPONENT]->(c:Component)-[:HAS_FINDING]->(f:Finding)-[:REPORTS_SUBSTANCE]->(s:Substance)
MATCH (f)-[:SUPPORTED_BY]->(d:SourceDocument)
RETURN b.name AS building, c.name AS component, s.name AS reported_substance, d.title AS source, f.source_page AS page
ORDER BY building, component;

MATCH (m:Material)<-[:MADE_OF]-(c:Component)<-[:HAS_COMPONENT]-(b:Building)
WHERE m.id = 'M001'
RETURN m.name AS material, collect(DISTINCT b.name + ': ' + c.name) AS locations;
