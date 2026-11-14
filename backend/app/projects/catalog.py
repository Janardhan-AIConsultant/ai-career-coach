"""Authored practical-project templates.

Each requirement/milestone has ``keywords`` that must appear (any one) in the evidence text
(README, pasted documentation, file paths) to count as *evidenced*. Evidence is a static review:
it shows the work is described/structured, not that it runs. ``kind="documentation"`` projects
(no code) are not scored on testing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    text: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class ProjectTemplate:
    id: str
    title: str
    kind: str  # "code" | "documentation"
    description: str
    skills: tuple[str, ...]  # taxonomy skill names / leadership categories this project practises
    requirements: tuple[Item, ...]
    expected_outcomes: tuple[str, ...]
    technologies: tuple[str, ...]
    milestones: tuple[Item, ...]
    difficulty: str = "intermediate"


def _i(text: str, *kw: str) -> Item:
    return Item(text, tuple(k.lower() for k in kw))


TEMPLATES: tuple[ProjectTemplate, ...] = (
    ProjectTemplate(
        "rag-qa-api", "RAG question-answering API", "code",
        "Build an API that ingests documents, indexes them in a vector store and answers questions with cited sources.",
        ("rag", "langchain", "chromadb", "fastapi", "python", "embeddings", "vector databases", "llm"),
        (_i("Document ingestion with chunking", "ingest", "chunk", "upload"),
         _i("Embeddings stored in a vector database", "embedding", "vector", "chroma", "faiss", "pgvector"),
         _i("Retrieval of relevant context for a question", "retriev", "similarity", "top-k", "top_k"),
         _i("Answers cite their sources", "citation", "cite", "source"),
         _i("Per-user data isolation or metadata filtering", "isolation", "tenant", "filter", "metadata")),
        ("A working API that answers questions grounded in your documents", "A short evaluation of answer quality"),
        ("Python", "FastAPI", "LangChain", "ChromaDB or pgvector"),
        (_i("Ingestion and chunking", "ingest", "chunk"), _i("Embedding and storage", "embedding", "vector"),
         _i("Retrieval endpoint", "retriev", "endpoint", "/query", "/ask"), _i("Evaluation and documentation", "evaluat", "readme"))),
    ProjectTemplate(
        "event-driven-orders", "Event-driven order processing", "code",
        "Two services (orders, payments) that communicate through a message broker with idempotent consumers.",
        ("kafka", "microservices", "postgresql", "docker", "distributed systems", "event-driven architecture"),
        (_i("Two or more services with clear boundaries", "service", "microservice"),
         _i("Asynchronous messaging between services", "kafka", "rabbitmq", "queue", "broker", "topic"),
         _i("Idempotent consumers or deduplication", "idempoten", "dedup", "duplicate"),
         _i("Reliable publishing (outbox) or retries/dead-letter handling", "outbox", "retry", "dead-letter", "dlq", "dead letter"),
         _i("Runs locally with Docker Compose", "docker-compose", "docker compose", "compose")),
        ("Orders flow from creation to payment without double processing", "A README explaining the failure scenarios handled"),
        ("Kafka or RabbitMQ", "PostgreSQL", "Docker Compose", "Python or Java"),
        (_i("Service skeletons", "service"), _i("Messaging", "kafka", "queue", "topic"), _i("Failure handling", "retry", "idempoten", "outbox"),
         _i("Compose setup and docs", "compose", "readme"))),
    ProjectTemplate(
        "secure-rest-api", "Secure REST API with authentication", "code",
        "A CRUD API with JWT authentication, role-based access control, validation, migrations and tests.",
        ("fastapi", "python", "postgresql", "rest apis", "spring boot", "java", "docker"),
        (_i("Authentication (e.g. JWT)", "jwt", "auth", "login", "token"),
         _i("Role-based authorization", "role", "rbac", "permission", "admin"),
         _i("Input validation", "validat", "pydantic", "schema", "bean validation"),
         _i("Database migrations", "migration", "alembic", "flyway", "liquibase"),
         _i("Automated tests", "pytest", "test", "junit")),
        ("An API where users can only access their own data", "Documented endpoints (OpenAPI or README)"),
        ("FastAPI or Spring Boot", "PostgreSQL", "pytest or JUnit"),
        (_i("CRUD endpoints", "crud", "endpoint", "route"), _i("Auth and roles", "jwt", "role"), _i("Tests", "test"), _i("Docs and deployment notes", "readme", "docker"))),
    ProjectTemplate(
        "cloud-deploy-pipeline", "Containerised app with CI/CD and infrastructure as code", "code",
        "Containerise a small service, build it in CI and deploy it to the cloud using infrastructure as code.",
        ("aws", "docker", "terraform", "ci/cd", "kubernetes", "github actions"),
        (_i("Dockerfile for the service", "dockerfile", "docker"),
         _i("CI pipeline that builds and tests", "github actions", "workflow", "ci", "pipeline", "jenkins"),
         _i("Infrastructure defined as code", "terraform", "cloudformation", "pulumi", "infrastructure as code"),
         _i("Deployment documentation and rollback notes", "deploy", "rollback"),
         _i("Secrets are not committed", "secret", ".env.example", "environment variable")),
        ("A push triggers build, test and deploy", "Repeatable infrastructure from code"),
        ("Docker", "GitHub Actions", "Terraform", "AWS or another cloud"),
        (_i("Containerise", "dockerfile"), _i("CI", "workflow", "pipeline"), _i("IaC", "terraform", "cloudformation"), _i("Deploy and document", "deploy", "readme"))),
    ProjectTemplate(
        "react-dashboard", "React dashboard with forms and tests", "code",
        "A responsive dashboard with validated forms, server-state fetching, accessibility basics and tests.",
        ("react", "typescript", "html/css", "tailwind", "next.js"),
        (_i("Component-based UI", "component"), _i("Form validation", "validat", "zod", "react-hook-form", "form"),
         _i("Data fetching with loading and error states", "fetch", "query", "axios", "loading", "error"),
         _i("Accessibility considerations", "accessib", "aria", "a11y"), _i("Automated UI tests", "vitest", "jest", "testing-library", "test")),
        ("A usable dashboard against a mock or real API", "Component and form tests"),
        ("React", "TypeScript", "Vite", "Vitest or Jest"),
        (_i("Layout and components", "component"), _i("Forms", "form", "validat"), _i("Data layer", "fetch", "query"), _i("Tests and docs", "test", "readme"))),
    ProjectTemplate(
        "system-design-doc", "System design document with a working prototype", "code",
        "Write a design for a scalable service (requirements, capacity estimation, architecture decisions) and prototype its riskiest part.",
        ("system design", "solution architecture", "distributed systems", "microservices", "caching"),
        (_i("Functional and non-functional requirements", "requirement", "non-functional", "nfr"),
         _i("Capacity estimation", "capacity", "estimation", "qps", "throughput"),
         _i("Architecture diagram or description", "diagram", "architecture", "c4"),
         _i("Architecture decision records or trade-offs", "adr", "decision", "trade-off", "tradeoff"),
         _i("A prototype of the riskiest component", "prototype", "poc", "proof of concept")),
        ("A reviewable design with justified trade-offs", "A prototype validating the main risk"),
        ("Any language for the prototype", "Mermaid or draw.io diagrams"),
        (_i("Requirements", "requirement"), _i("Design", "architecture", "diagram"), _i("Decisions", "adr", "decision"), _i("Prototype", "prototype", "poc"))),
    ProjectTemplate(
        "team-playbook", "Engineering team playbook", "documentation",
        "Write a practical playbook for a team: onboarding, code review, decision records, incident response and 1:1 practices.",
        ("mentoring", "team_management", "delivery_management", "technical_leadership", "risk_management"),
        (_i("Onboarding plan", "onboarding", "30/60/90"), _i("Code review guidelines", "code review", "review"),
         _i("Decision record template", "adr", "decision record"), _i("Incident response and post-mortem process", "incident", "post-mortem", "postmortem"),
         _i("Feedback and 1:1 practices", "1:1", "one-on-one", "feedback")),
        ("A reusable playbook a new team could adopt", "Templates for ADRs and post-mortems"),
        ("Markdown", "A shared repository"),
        (_i("Onboarding and reviews", "onboarding", "review"), _i("Decisions and incidents", "adr", "incident"), _i("People practices", "feedback", "1:1")),
    ),
)
BY_ID = {t.id: t for t in TEMPLATES}
