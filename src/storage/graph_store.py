from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.schemas import MemoryCore


if TYPE_CHECKING:
    from src.domains.project_decision.models import ProjectDecision


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Neo4jGraphConfig:
    """Connection settings for the Neo4j graph index."""

    uri: str = "bolt://localhost:7687"
    username: str = "neo4j"
    password: str = "password"
    database: str | None = None


class Neo4jGraphStore:
    """Neo4j-backed side index for memory relationships.

    SQLite remains the source of truth. This store mirrors selected memory,
    entity, context, and lifecycle edges for graph retrieval and visualization.
    """

    def __init__(
        self,
        config: Neo4jGraphConfig,
        driver: Any | None = None,
    ) -> None:
        """Create a graph store with a real Neo4j driver or an injected test driver."""
        self.config = config
        if driver is not None:
            self.driver = driver
            return

        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise RuntimeError(
                "Neo4jGraphStore requires the optional 'neo4j' package. "
                "Install project requirements before enabling graph storage."
            ) from exc

        self.driver = GraphDatabase.driver(
            config.uri,
            auth=(config.username, config.password),
        )

    def close(self) -> None:
        """Close the underlying Neo4j driver and release its network resources."""
        self.driver.close()

    def create_schema(self) -> None:
        """Create Neo4j constraints and indexes for graph index persistence."""
        statements = [
            """
            CREATE CONSTRAINT memory_id_unique IF NOT EXISTS
            FOR (m:Memory) REQUIRE m.memory_id IS UNIQUE
            """,
            """
            CREATE CONSTRAINT entity_key_unique IF NOT EXISTS
            FOR (e:Entity) REQUIRE (e.name, e.type) IS UNIQUE
            """,
            """
            CREATE CONSTRAINT decision_id_unique IF NOT EXISTS
            FOR (d:Decision) REQUIRE d.decision_id IS UNIQUE
            """,
            """
            CREATE CONSTRAINT project_id_unique IF NOT EXISTS
            FOR (p:Project) REQUIRE p.project_id IS UNIQUE
            """,
            """
            CREATE CONSTRAINT user_id_unique IF NOT EXISTS
            FOR (u:User) REQUIRE u.user_id IS UNIQUE
            """,
            """
            CREATE CONSTRAINT team_id_unique IF NOT EXISTS
            FOR (t:Team) REQUIRE t.team_id IS UNIQUE
            """,
            """
            CREATE CONSTRAINT workspace_id_unique IF NOT EXISTS
            FOR (w:Workspace) REQUIRE w.workspace_id IS UNIQUE
            """,
            """
            CREATE INDEX memory_domain_status IF NOT EXISTS
            FOR (m:Memory) ON (m.domain, m.status)
            """,
            """
            CREATE INDEX decision_project_status IF NOT EXISTS
            FOR (d:Decision) ON (d.project_id, d.status)
            """,
        ]
        for statement in statements:
            self._run_write(statement)

    def upsert_memory(self, memory: MemoryCore) -> str:
        """Persist a Memory node and mirror basic entity/lifecycle relationships."""
        logger.info(
            "function=src.storage.graph_store.Neo4jGraphStore.upsert_memory action=start memory_id=%s domain=%s status=%s",
            memory.memory_id,
            memory.domain,
            memory.status,
        )
        self._run_write(
            """
            MERGE (m:Memory {memory_id: $memory_id})
            SET m.domain = $domain,
                m.memory_type = $memory_type,
                m.scope = $scope,
                m.source_type = $source_type,
                m.source_ref = $source_ref,
                m.source_event_id = $source_event_id,
                m.content_text = $content_text,
                m.summary_text = $summary_text,
                m.tags = $tags,
                m.importance = $importance,
                m.confidence = $confidence,
                m.status = $status,
                m.valid_from = $valid_from,
                m.valid_to = $valid_to,
                m.created_at = $created_at,
                m.updated_at = $updated_at
            """,
            {
                "memory_id": memory.memory_id,
                "domain": memory.domain,
                "memory_type": memory.memory_type,
                "scope": memory.scope,
                "source_type": memory.source_type,
                "source_ref": memory.source_ref,
                "source_event_id": memory.source_event_id,
                "content_text": memory.content_text,
                "summary_text": memory.summary_text,
                "tags": memory.tags,
                "importance": memory.importance,
                "confidence": memory.confidence,
                "status": memory.status,
                "valid_from": memory.valid_from,
                "valid_to": memory.valid_to,
                "created_at": memory.created_at,
                "updated_at": memory.updated_at,
            },
        )
        self.link_memory_entities(memory.memory_id, memory.entities)
        if memory.superseded_by is not None:
            self.link_supersedes(memory.memory_id, memory.superseded_by)
        if memory.overwrite_of is not None:
            self.link_supersedes(memory.overwrite_of, memory.memory_id)
        return memory.memory_id

    def link_memory_entities(self, memory_id: str, entities: list[str]) -> None:
        """Link a persisted Memory node to normalized Entity nodes via MENTIONS edges."""
        unique_entities = sorted({entity.strip() for entity in entities if entity.strip()})
        if not unique_entities:
            return
        self._run_write(
            """
            MATCH (m:Memory {memory_id: $memory_id})
            UNWIND $entities AS entity_name
            MERGE (e:Entity {name: entity_name, type: 'generic'})
            MERGE (m)-[:MENTIONS]->(e)
            """,
            {
                "memory_id": memory_id,
                "entities": unique_entities,
            },
        )

    def link_memory_context(
        self,
        memory_id: str,
        *,
        project_id: str | None = None,
        team_id: str | None = None,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ) -> None:
        """Link a Memory node to project/team/workspace/user context nodes."""
        if project_id is not None:
            self._link_context_node(memory_id, "Project", "project_id", project_id, "BELONGS_TO")
        if team_id is not None:
            self._link_context_node(memory_id, "Team", "team_id", team_id, "BELONGS_TO")
        if workspace_id is not None:
            self._link_context_node(
                memory_id,
                "Workspace",
                "workspace_id",
                workspace_id,
                "BELONGS_TO",
            )
        if user_id is not None:
            self._link_context_node(memory_id, "User", "user_id", user_id, "CREATED_BY")

    def link_supersedes(self, old_memory_id: str, new_memory_id: str) -> None:
        """Link a newer Memory node to the older Memory node it supersedes."""
        self._run_write(
            """
            MATCH (old:Memory {memory_id: $old_memory_id})
            MATCH (new:Memory {memory_id: $new_memory_id})
            MERGE (new)-[:SUPERSEDES]->(old)
            """,
            {
                "old_memory_id": old_memory_id,
                "new_memory_id": new_memory_id,
            },
        )

    def upsert_project_decision(
        self,
        decision: ProjectDecision,
        *,
        decided_by: str | None = None,
        memory_id: str | None = None,
    ) -> str:
        """Persist a project decision subgraph.

        The decision node is linked back to its Memory node when available. If
        no explicit decider is provided, participants are treated as decision
        makers for the graph index so user-centric traversal has useful edges.
        """
        target_memory_id = memory_id or decision.decision_id
        self._run_write(
            """
            MERGE (d:Decision {decision_id: $decision_id})
            SET d.project_id = $project_id,
                d.workspace_id = $workspace_id,
                d.team_id = $team_id,
                d.thread_id = $thread_id,
                d.topic = $topic,
                d.decision = $decision,
                d.conclusion = $conclusion,
                d.stage = $stage,
                d.status = $status,
                d.source_event_id = $source_event_id,
                d.source_type = $source_type,
                d.source_ref = $source_ref,
                d.decided_at = $decided_at,
                d.valid_from = $valid_from,
                d.valid_to = $valid_to,
                d.tags = $tags,
                d.confidence = $confidence,
                d.importance = $importance
            WITH d
            OPTIONAL MATCH (m:Memory {memory_id: $memory_id})
            FOREACH (_ IN CASE WHEN m IS NULL THEN [] ELSE [1] END |
                MERGE (d)-[:RECORDED_AS]->(m)
            )
            """,
            {
                "decision_id": decision.decision_id,
                "project_id": decision.project_id,
                "workspace_id": decision.workspace_id,
                "team_id": decision.team_id,
                "thread_id": decision.thread_id,
                "topic": decision.topic,
                "decision": decision.decision,
                "conclusion": decision.conclusion,
                "stage": decision.stage,
                "status": decision.status,
                "source_event_id": decision.source_event_id,
                "source_type": decision.source_type,
                "source_ref": decision.source_ref,
                "decided_at": decision.decided_at,
                "valid_from": decision.valid_from,
                "valid_to": decision.valid_to,
                "tags": decision.tags,
                "confidence": decision.confidence,
                "importance": decision.importance,
                "memory_id": target_memory_id,
            },
        )
        self._link_decision_context(decision)
        self._link_decision_makers(decision, decided_by=decided_by)
        if decision.overwrite_of is not None:
            self.link_decision_supersedes(decision.overwrite_of, decision.decision_id)
        return decision.decision_id

    def link_decision_supersedes(self, old_decision_id: str, new_decision_id: str) -> None:
        """Link a newer Decision node to the older Decision node it supersedes."""
        self._run_write(
            """
            MATCH (old:Decision {decision_id: $old_decision_id})
            MATCH (new:Decision {decision_id: $new_decision_id})
            MERGE (new)-[:SUPERSEDES]->(old)
            """,
            {
                "old_decision_id": old_decision_id,
                "new_decision_id": new_decision_id,
            },
        )

    def get_version_chain(self, memory_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Return Memory nodes connected by SUPERSEDES edges around one memory."""
        return self._run_read(
            """
            MATCH (start:Memory {memory_id: $memory_id})
            MATCH path = (start)-[:SUPERSEDES*0..]-(m:Memory)
            WITH DISTINCT m
            RETURN m.memory_id AS memory_id,
                   m.domain AS domain,
                   m.memory_type AS memory_type,
                   m.status AS status,
                   m.content_text AS content_text,
                   m.created_at AS created_at,
                   m.updated_at AS updated_at
            ORDER BY coalesce(m.created_at, ''), coalesce(m.updated_at, ''), m.memory_id
            LIMIT $limit
            """,
            {
                "memory_id": memory_id,
                "limit": limit,
            },
        )

    def find_memories_by_entity(
        self,
        entity_name: str,
        *,
        entity_type: str = "generic",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Find active Memory nodes that mention a specific Entity."""
        return self._run_read(
            """
            MATCH (m:Memory)-[:MENTIONS]->(e:Entity {name: $entity_name, type: $entity_type})
            WHERE m.status = 'active'
            RETURN m.memory_id AS memory_id,
                   m.domain AS domain,
                   m.memory_type AS memory_type,
                   m.content_text AS content_text,
                   m.importance AS importance,
                   m.confidence AS confidence,
                   e.name AS entity_name
            ORDER BY m.importance DESC, m.confidence DESC, m.updated_at DESC
            LIMIT $limit
            """,
            {
                "entity_name": entity_name,
                "entity_type": entity_type,
                "limit": limit,
            },
        )

    def find_decisions_by_user(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Find decisions made by one user through MADE_DECISION edges."""
        return self._run_read(
            """
            MATCH (u:User {user_id: $user_id})-[r:MADE_DECISION]->(d:Decision)
            OPTIONAL MATCH (d)-[:BELONGS_TO]->(p:Project)
            OPTIONAL MATCH (d)-[:RECORDED_AS]->(m:Memory)
            RETURN d.decision_id AS decision_id,
                   d.topic AS topic,
                   d.decision AS decision,
                   d.status AS status,
                   d.stage AS stage,
                   d.decided_at AS decided_at,
                   d.source_event_id AS source_event_id,
                   d.source_ref AS source_ref,
                   p.project_id AS project_id,
                   m.memory_id AS memory_id,
                   r.role AS role
            ORDER BY d.decided_at DESC, d.decision_id
            LIMIT $limit
            """,
            {
                "user_id": user_id,
                "limit": limit,
            },
        )

    def find_project_decisions(self, project_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Find decisions belonging to a project and include their decider ids."""
        return self._run_read(
            """
            MATCH (d:Decision)-[:BELONGS_TO]->(p:Project {project_id: $project_id})
            OPTIONAL MATCH (u:User)-[:MADE_DECISION]->(d)
            OPTIONAL MATCH (d)-[:RECORDED_AS]->(m:Memory)
            RETURN d.decision_id AS decision_id,
                   d.topic AS topic,
                   d.decision AS decision,
                   d.status AS status,
                   d.stage AS stage,
                   d.decided_at AS decided_at,
                   d.source_event_id AS source_event_id,
                   d.source_ref AS source_ref,
                   collect(DISTINCT u.user_id) AS decided_by,
                   m.memory_id AS memory_id
            ORDER BY d.decided_at DESC, d.importance DESC, d.decision_id
            LIMIT $limit
            """,
            {
                "project_id": project_id,
                "limit": limit,
            },
        )

    def find_project_context(self, project_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Find active memories under a project with their mentioned entities."""
        return self._run_read(
            """
            MATCH (m:Memory)-[:BELONGS_TO]->(p:Project {project_id: $project_id})
            WHERE m.status = 'active'
            OPTIONAL MATCH (m)-[:MENTIONS]->(e:Entity)
            RETURN m.memory_id AS memory_id,
                   m.domain AS domain,
                   m.memory_type AS memory_type,
                   m.content_text AS content_text,
                   collect(DISTINCT e.name) AS entities,
                   m.importance AS importance,
                   m.confidence AS confidence
            ORDER BY m.importance DESC, m.confidence DESC, m.updated_at DESC
            LIMIT $limit
            """,
            {
                "project_id": project_id,
                "limit": limit,
            },
        )

    def _link_decision_context(self, decision: ProjectDecision) -> None:
        """Link a Decision node to available project/team/workspace context nodes."""
        if decision.project_id is not None:
            self._link_decision_context_node(
                decision.decision_id,
                "Project",
                "project_id",
                decision.project_id,
            )
        if decision.team_id is not None:
            self._link_decision_context_node(
                decision.decision_id,
                "Team",
                "team_id",
                decision.team_id,
            )
        if decision.workspace_id is not None:
            self._link_decision_context_node(
                decision.decision_id,
                "Workspace",
                "workspace_id",
                decision.workspace_id,
            )

    def _link_decision_context_node(
        self,
        decision_id: str,
        label: str,
        key: str,
        value: str,
    ) -> None:
        """Safely create one BELONGS_TO edge from Decision to an allowed context label."""
        allowed_labels = {"Project", "Team", "Workspace"}
        if label not in allowed_labels:
            raise ValueError("Unsupported decision context label")
        self._run_write(
            f"""
            MATCH (d:Decision {{decision_id: $decision_id}})
            MERGE (n:{label} {{{key}: $value}})
            MERGE (d)-[:BELONGS_TO]->(n)
            """,
            {
                "decision_id": decision_id,
                "value": value,
            },
        )

    def _link_decision_makers(
        self,
        decision: ProjectDecision,
        *,
        decided_by: str | None,
    ) -> None:
        """Create MADE_DECISION edges from explicit decider or decision participants."""
        user_ids = [decided_by] if decided_by else decision.participants
        unique_user_ids = sorted({user_id.strip() for user_id in user_ids if user_id.strip()})
        if not unique_user_ids:
            return
        self._run_write(
            """
            MATCH (d:Decision {decision_id: $decision_id})
            UNWIND $user_ids AS user_id
            MERGE (u:User {user_id: user_id})
            MERGE (u)-[r:MADE_DECISION]->(d)
            SET r.source_event_id = $source_event_id,
                r.source_ref = $source_ref,
                r.decided_at = $decided_at,
                r.role = $role
            """,
            {
                "decision_id": decision.decision_id,
                "user_ids": unique_user_ids,
                "source_event_id": decision.source_event_id,
                "source_ref": decision.source_ref,
                "decided_at": decision.decided_at,
                "role": "decider",
            },
        )

    def _link_context_node(
        self,
        memory_id: str,
        label: str,
        key: str,
        value: str,
        relationship: str,
    ) -> None:
        """Safely create one context edge from Memory to an allowed context label."""
        allowed_labels = {"Project", "Team", "Workspace", "User"}
        allowed_relationships = {"BELONGS_TO", "CREATED_BY"}
        if label not in allowed_labels or relationship not in allowed_relationships:
            raise ValueError("Unsupported graph context label or relationship")
        self._run_write(
            f"""
            MATCH (m:Memory {{memory_id: $memory_id}})
            MERGE (n:{label} {{{key}: $value}})
            MERGE (m)-[:{relationship}]->(n)
            """,
            {
                "memory_id": memory_id,
                "value": value,
            },
        )

    def _run_write(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a Cypher write statement against Neo4j."""
        return self._run(query, parameters or {})

    def _run_read(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a Cypher read statement and return records as plain dicts."""
        return self._run(query, parameters or {})

    def _run(self, query: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
        """Run Cypher in the configured Neo4j database using the driver's session."""
        session_kwargs: dict[str, Any] = {}
        if self.config.database is not None:
            session_kwargs["database"] = self.config.database
        with self.driver.session(**session_kwargs) as session:
            result = session.run(query, parameters)
            return [dict(record) for record in result]
