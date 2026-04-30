from __future__ import annotations

import unittest
from typing import Any

from src.domains.project_decision.models import ProjectDecision
from src.schemas import MemoryCore
from src.storage import Neo4jGraphConfig, Neo4jGraphStore


class FakeNeo4jSession:
    def __init__(self, driver: "FakeNeo4jDriver") -> None:
        self.driver = driver

    def __enter__(self) -> "FakeNeo4jSession":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def run(self, query: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
        self.driver.calls.append(
            {
                "query": " ".join(query.split()),
                "parameters": parameters,
            }
        )
        return self.driver.results.pop(0) if self.driver.results else []


class FakeNeo4jDriver:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.results: list[list[dict[str, Any]]] = []
        self.closed = False
        self.session_kwargs: list[dict[str, Any]] = []

    def session(self, **kwargs: Any) -> FakeNeo4jSession:
        self.session_kwargs.append(kwargs)
        return FakeNeo4jSession(self)

    def close(self) -> None:
        self.closed = True


class TestNeo4jGraphStore(unittest.TestCase):
    def setUp(self) -> None:
        self.driver = FakeNeo4jDriver()
        self.store = Neo4jGraphStore(
            Neo4jGraphConfig(database="neo4j"),
            driver=self.driver,
        )

    def test_create_schema_creates_constraints_and_indexes(self) -> None:
        self.store.create_schema()

        queries = [call["query"] for call in self.driver.calls]

        self.assertTrue(any("CONSTRAINT memory_id_unique" in query for query in queries))
        self.assertTrue(any("CONSTRAINT entity_key_unique" in query for query in queries))
        self.assertTrue(any("CONSTRAINT decision_id_unique" in query for query in queries))
        self.assertTrue(any("INDEX memory_domain_status" in query for query in queries))
        self.assertTrue(any("INDEX decision_project_status" in query for query in queries))
        self.assertEqual(self.driver.session_kwargs[0], {"database": "neo4j"})

    def test_upsert_memory_merges_memory_entities_and_supersede_edges(self) -> None:
        memory = MemoryCore(
            memory_id="memory-new",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-1",
            content_text="Use Neo4j as the graph side index",
            entities=["Neo4j", "graph", "Neo4j"],
            tags=["storage"],
            importance=0.8,
            confidence=0.9,
            overwrite_of="memory-old",
        )

        inserted_id = self.store.upsert_memory(memory)

        self.assertEqual(inserted_id, "memory-new")
        self.assertEqual(self.driver.calls[0]["parameters"]["memory_id"], "memory-new")
        self.assertIn("MERGE (m:Memory", self.driver.calls[0]["query"])
        self.assertEqual(
            self.driver.calls[1]["parameters"],
            {
                "memory_id": "memory-new",
                "entities": ["Neo4j", "graph"],
            },
        )
        self.assertEqual(
            self.driver.calls[2]["parameters"],
            {
                "old_memory_id": "memory-old",
                "new_memory_id": "memory-new",
            },
        )

    def test_link_memory_context_uses_fixed_labels_and_relationships(self) -> None:
        self.store.link_memory_context(
            "memory-1",
            project_id="project-1",
            team_id="team-1",
            workspace_id="workspace-1",
            user_id="user-1",
        )

        queries = [call["query"] for call in self.driver.calls]

        self.assertIn("MERGE (n:Project {project_id: $value})", queries[0])
        self.assertIn("MERGE (n:Team {team_id: $value})", queries[1])
        self.assertIn("MERGE (n:Workspace {workspace_id: $value})", queries[2])
        self.assertIn("MERGE (n:User {user_id: $value})", queries[3])
        self.assertIn("MERGE (m)-[:CREATED_BY]->(n)", queries[3])

    def test_get_version_chain_returns_rows(self) -> None:
        self.driver.results.append(
            [
                {"memory_id": "memory-old", "status": "superseded"},
                {"memory_id": "memory-new", "status": "active"},
            ]
        )

        rows = self.store.get_version_chain("memory-new")

        self.assertEqual([row["memory_id"] for row in rows], ["memory-old", "memory-new"])
        self.assertIn("SUPERSEDES*0..", self.driver.calls[0]["query"])
        self.assertEqual(self.driver.calls[0]["parameters"]["memory_id"], "memory-new")

    def test_find_memories_by_entity_returns_active_memory_rows(self) -> None:
        self.driver.results.append(
            [
                {
                    "memory_id": "memory-1",
                    "domain": "project_decision",
                    "entity_name": "Neo4j",
                }
            ]
        )

        rows = self.store.find_memories_by_entity("Neo4j", limit=5)

        self.assertEqual(rows[0]["memory_id"], "memory-1")
        self.assertIn("MENTIONS", self.driver.calls[0]["query"])
        self.assertEqual(self.driver.calls[0]["parameters"]["entity_name"], "Neo4j")
        self.assertEqual(self.driver.calls[0]["parameters"]["limit"], 5)

    def test_find_project_context_returns_memory_rows_with_entities(self) -> None:
        self.driver.results.append(
            [
                {
                    "memory_id": "memory-1",
                    "domain": "team_retention",
                    "entities": ["owner", "deadline"],
                }
            ]
        )

        rows = self.store.find_project_context("project-1", limit=3)

        self.assertEqual(rows[0]["entities"], ["owner", "deadline"])
        self.assertIn("Project {project_id: $project_id}", self.driver.calls[0]["query"])
        self.assertEqual(self.driver.calls[0]["parameters"]["project_id"], "project-1")

    def test_upsert_project_decision_merges_decision_context_and_decider(self) -> None:
        decision = ProjectDecision(
            decision_id="decision-1",
            project_id="project-1",
            workspace_id="workspace-1",
            team_id="team-1",
            topic="graph index",
            decision="Use Neo4j for relationship traversal",
            status="confirmed",
            source_event_id="event-1",
            source_ref="thread-1",
            decided_at="2026-04-27T20:00:00Z",
            confidence=0.9,
            importance=0.8,
        )

        decision_id = self.store.upsert_project_decision(decision, decided_by="user-1")

        self.assertEqual(decision_id, "decision-1")
        self.assertIn("MERGE (d:Decision", self.driver.calls[0]["query"])
        self.assertIn("RECORDED_AS", self.driver.calls[0]["query"])
        self.assertEqual(self.driver.calls[0]["parameters"]["decision_id"], "decision-1")
        self.assertEqual(self.driver.calls[0]["parameters"]["memory_id"], "decision-1")
        self.assertIn("MERGE (n:Project {project_id: $value})", self.driver.calls[1]["query"])
        self.assertIn("MERGE (n:Team {team_id: $value})", self.driver.calls[2]["query"])
        self.assertIn("MERGE (n:Workspace {workspace_id: $value})", self.driver.calls[3]["query"])
        self.assertIn("MADE_DECISION", self.driver.calls[4]["query"])
        self.assertEqual(self.driver.calls[4]["parameters"]["user_ids"], ["user-1"])
        self.assertEqual(self.driver.calls[4]["parameters"]["source_event_id"], "event-1")

    def test_upsert_project_decision_allows_explicit_decider(self) -> None:
        decision = ProjectDecision(
            decision_id="decision-1",
            project_id="project-1",
            topic="graph index",
            decision="Use Neo4j",
        )

        self.store.upsert_project_decision(
            decision,
            decided_by="owner-1",
            memory_id="memory-1",
        )

        self.assertEqual(self.driver.calls[0]["parameters"]["memory_id"], "memory-1")
        self.assertEqual(self.driver.calls[2]["parameters"]["user_ids"], ["owner-1"])

    def test_upsert_project_decision_links_superseded_decision(self) -> None:
        decision = ProjectDecision(
            decision_id="decision-new",
            project_id="project-1",
            topic="graph index",
            decision="Use Neo4j",
            overwrite_of="decision-old",
        )

        self.store.upsert_project_decision(decision)

        self.assertIn("SUPERSEDES", self.driver.calls[-1]["query"])
        self.assertEqual(
            self.driver.calls[-1]["parameters"],
            {
                "old_decision_id": "decision-old",
                "new_decision_id": "decision-new",
            },
        )

    def test_find_decisions_by_user_returns_decision_rows(self) -> None:
        self.driver.results.append(
            [
                {
                    "decision_id": "decision-1",
                    "topic": "graph index",
                    "memory_id": "memory-1",
                    "role": "decider",
                }
            ]
        )

        rows = self.store.find_decisions_by_user("user-1", limit=5)

        self.assertEqual(rows[0]["decision_id"], "decision-1")
        self.assertIn("MADE_DECISION", self.driver.calls[0]["query"])
        self.assertEqual(self.driver.calls[0]["parameters"]["user_id"], "user-1")
        self.assertEqual(self.driver.calls[0]["parameters"]["limit"], 5)

    def test_find_project_decisions_returns_decider_ids(self) -> None:
        self.driver.results.append(
            [
                {
                    "decision_id": "decision-1",
                    "topic": "graph index",
                    "decided_by": ["user-1"],
                    "memory_id": "memory-1",
                }
            ]
        )

        rows = self.store.find_project_decisions("project-1", limit=5)

        self.assertEqual(rows[0]["decided_by"], ["user-1"])
        self.assertIn("Decision)-[:BELONGS_TO]->(p:Project", self.driver.calls[0]["query"])
        self.assertIn("MADE_DECISION", self.driver.calls[0]["query"])
        self.assertEqual(self.driver.calls[0]["parameters"]["project_id"], "project-1")

    def test_close_closes_driver(self) -> None:
        self.store.close()

        self.assertTrue(self.driver.closed)
