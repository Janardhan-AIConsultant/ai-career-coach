"""Skill and leadership taxonomy used for deterministic, hallucination-free extraction.

Skills are only ever *detected in text* (never invented). ``SKILL_GROUPS`` maps a group name to
``{canonical skill: aliases}``. Matching is word-boundary based and case-insensitive.
``TECHNICAL_GROUPS``/``ARCHITECTURE_GROUPS``/``TOOL_GROUPS`` drive category scoring.
"""

from __future__ import annotations

import re
from functools import lru_cache

SKILL_GROUPS: dict[str, dict[str, tuple[str, ...]]] = {
    "programming_languages": {
        "python": ("python",), "java": ("java",), "javascript": ("javascript", "ecmascript"),
        "typescript": ("typescript",), "c#": ("c#", "csharp"), "c++": ("c++",),
        "go": ("golang",), "rust": ("rust",), "kotlin": ("kotlin",), "scala": ("scala",),
        "ruby": ("ruby",), "php": ("php",), "sql": ("sql", "plsql", "pl/sql", "t-sql"),
    },
    "backend": {
        "spring boot": ("spring boot", "springboot", "spring framework"),
        "fastapi": ("fastapi",), "django": ("django",), "flask": ("flask",),
        "node.js": ("node.js", "nodejs", "node js"), "express.js": ("express.js", "expressjs"),
        ".net": (".net", "dotnet", "asp.net"), "rest apis": ("rest api", "rest apis", "restful"),
        "graphql": ("graphql",), "grpc": ("grpc",), "hibernate": ("hibernate", "jpa"),
    },
    "frontend": {
        "react": ("react", "react.js", "reactjs"), "angular": ("angular",), "vue": ("vue", "vue.js"),
        "html/css": ("html", "css", "html5", "css3"), "redux": ("redux",),
        "next.js": ("next.js", "nextjs"), "tailwind": ("tailwind", "tailwindcss"),
    },
    "databases": {
        "postgresql": ("postgresql", "postgres"), "mysql": ("mysql",), "mongodb": ("mongodb",),
        "redis": ("redis",), "oracle": ("oracle db", "oracle database"), "sql server": ("sql server", "mssql"),
        "dynamodb": ("dynamodb",), "cassandra": ("cassandra",), "elasticsearch": ("elasticsearch", "opensearch"),
    },
    "cloud": {
        "aws": ("aws", "amazon web services"), "azure": ("azure",), "gcp": ("gcp", "google cloud"),
        "aws lambda": ("lambda",), "amazon s3": ("s3",), "ec2": ("ec2",), "eks": ("eks",),
        "bedrock": ("bedrock",), "cloudformation": ("cloudformation",),
    },
    "microservices": {
        "microservices": ("microservice", "microservices", "micro-services"),
        "api gateway": ("api gateway",), "service mesh": ("service mesh", "istio"),
        "saga pattern": ("saga pattern", "saga"),
    },
    "distributed_systems": {
        "distributed systems": ("distributed system", "distributed systems"),
        "event-driven architecture": ("event-driven", "event driven", "event sourcing"),
        "cqrs": ("cqrs",), "high availability": ("high availability", "fault tolerance", "fault-tolerant"),
    },
    "messaging": {
        "kafka": ("kafka",), "rabbitmq": ("rabbitmq",), "amazon sqs/sns": ("sqs", "sns"),
        "activemq": ("activemq",), "kinesis": ("kinesis",), "pub/sub": ("pub/sub", "pubsub"),
    },
    "ai_genai": {
        "machine learning": ("machine learning", "ml models"), "deep learning": ("deep learning",),
        "generative ai": ("generative ai", "genai", "gen ai"), "llm": ("llm", "llms", "large language model"),
        "prompt engineering": ("prompt engineering",), "langchain": ("langchain",),
        "langgraph": ("langgraph",), "nlp": ("nlp", "natural language processing"),
        "pytorch": ("pytorch",), "tensorflow": ("tensorflow",), "scikit-learn": ("scikit-learn", "sklearn"),
        "openai": ("openai",), "pandas": ("pandas",), "numpy": ("numpy",),
    },
    "rag": {
        "rag": ("rag", "retrieval augmented generation", "retrieval-augmented generation"),
        "embeddings": ("embedding", "embeddings"), "reranking": ("reranking", "re-ranking"),
    },
    "vector_databases": {
        "chromadb": ("chromadb", "chroma db"), "pinecone": ("pinecone",), "pgvector": ("pgvector",),
        "faiss": ("faiss",), "weaviate": ("weaviate",), "milvus": ("milvus",), "qdrant": ("qdrant",),
        "vector databases": ("vector database", "vector databases", "vector db", "vector store"),
    },
    "system_design": {
        "system design": ("system design",), "scalability": ("scalability", "scalable systems"),
        "caching": ("caching",), "load balancing": ("load balancing", "load balancer"),
    },
    "solution_architecture": {
        "solution architecture": ("solution architecture", "solutions architecture", "solution architect"),
        "enterprise architecture": ("enterprise architecture",),
        "domain-driven design": ("domain-driven design", "ddd"), "togaf": ("togaf",),
    },
    "devops_tools": {
        "docker": ("docker",), "kubernetes": ("kubernetes", "k8s"), "terraform": ("terraform",),
        "jenkins": ("jenkins",), "github actions": ("github actions",), "ci/cd": ("ci/cd", "cicd"),
        "git": ("git", "github", "gitlab"), "linux": ("linux",), "ansible": ("ansible",),
        "maven": ("maven",), "gradle": ("gradle",), "jira": ("jira",),
    },
}

ARCHITECTURE_GROUPS = {"microservices", "distributed_systems", "system_design", "solution_architecture"}
TOOL_GROUPS = {"devops_tools"}
TECHNICAL_GROUPS = set(SKILL_GROUPS) - ARCHITECTURE_GROUPS - TOOL_GROUPS

# Groups whose members are plausible substitutes for each other, with the partial credit given
# when the resume evidences a *different* skill of the same group (e.g. RabbitMQ requested, Kafka
# shown). Broad groups (devops tools, AI libraries, architecture topics) get no partial credit.
PARTIAL_CREDIT: dict[str, float] = {
    "programming_languages": 0.25,
    "backend": 0.5,
    "frontend": 0.25,
    "databases": 0.5,
    "cloud": 0.5,
    "messaging": 0.5,
    "vector_databases": 0.5,
}

LEADERSHIP_CATEGORIES: dict[str, tuple[str, ...]] = {
    "engineering_management": (
        r"engineering manager", r"head of engineering", r"director of engineering", r"headcount",
        r"\bokrs?\b", r"\bbudget(s|ing)?\b", r"people management",
    ),
    "technical_leadership": (
        r"tech(nical)? lead", r"technical direction", r"design reviews?", r"technical roadmap",
        r"led (the )?technical", r"principal engineer",
    ),
    "team_management": (
        r"\b(led|lead|leading|managed|managing|headed)\b[^.\n]{0,40}\b(team|engineers|developers|squad|group)\b",
        r"team of \d+", r"\bhiring\b", r"performance reviews?", r"direct reports?",
    ),
    "stakeholder_communication": (
        r"stakeholders?", r"\bexecutives?\b", r"client[- ]facing", r"presented to", r"cross-functional",
    ),
    "delivery_management": (
        r"\bdelivery\b", r"\bsprints?\b", r"\bscrum\b", r"\bagile\b", r"\bmilestones?\b",
        r"release (management|planning)", r"\bon[- ]time\b",
    ),
    "architecture_decisions": (
        r"architected", r"architecture decisions?", r"\badrs?\b", r"designed the architecture",
        r"technical design", r"architecture (review|governance)",
    ),
    "mentoring": (r"\bmentor(ed|ing|s)?\b", r"\bcoach(ed|ing)\b", r"onboard(ed|ing)", r"grew (junior|engineers)"),
    "conflict_resolution": (r"\bconflicts?\b", r"resolved disagreements?", r"\bmediat(e|ed|ion)\b", r"\bnegotiat(e|ed|ion)\b"),
    "strategic_thinking": (r"\bstrateg(y|ic|ies)\b", r"\bvision\b", r"long[- ]term", r"technology strategy"),
    "risk_management": (r"risk (management|assessment|mitigation)", r"\bmitigat(e|ed|ion)\b", r"contingency", r"incident (response|management)"),
}

DOMAINS = (
    "fintech", "banking", "payments", "insurance", "healthcare", "e-commerce", "ecommerce", "retail",
    "telecom", "logistics", "supply chain", "gaming", "edtech", "saas", "adtech", "automotive",
    "manufacturing", "energy", "media", "travel", "real estate", "cybersecurity",
)

CERTIFICATIONS = {
    "aws certified": r"aws certified[\w\s-]{0,40}", "azure certified": r"(microsoft )?azure[\w\s-]{0,20}(certified|az-\d+)",
    "gcp certified": r"google cloud[\w\s-]{0,20}certified", "pmp": r"\bpmp\b", "cissp": r"\bcissp\b",
    "scrum master": r"(certified )?scrum master|\bcsm\b|\bpsm\b", "kubernetes certified": r"\b(ckad|cka|cks)\b|certified kubernetes",
    "togaf": r"\btogaf\b", "oracle certified": r"oracle certified", "safe": r"\bsafe (agilist|certified)",
}

EDUCATION_LEVELS = {
    "doctorate": (5, r"\b(ph\.?d|doctorate|doctoral)\b"),
    "master's": (4, r"\b(master'?s?|m\.?tech|m\.?s\.?c?|mba|m\.?e\.?|mca)\b(?!\w)"),
    "bachelor's": (3, r"\b(bachelor'?s?|b\.?tech|b\.?e\.?|b\.?s\.?c?|bca|b\.?com|undergraduate)\b"),
    "diploma": (2, r"\bdiploma\b"),
}


@lru_cache
def skill_patterns() -> dict[str, tuple[str, re.Pattern[str]]]:
    """canonical skill -> (group, compiled alternation of its aliases)."""
    out: dict[str, tuple[str, re.Pattern[str]]] = {}
    for group, skills in SKILL_GROUPS.items():
        for canonical, aliases in skills.items():
            alt = "|".join(
                rf"(?<![A-Za-z0-9+#]){re.escape(a)}(?![A-Za-z0-9+#]|\.[A-Za-z0-9])"
                for a in sorted(aliases, key=len, reverse=True)
            )
            out[canonical] = (group, re.compile(alt, re.IGNORECASE))
    return out


@lru_cache
def leadership_patterns() -> dict[str, list[re.Pattern[str]]]:
    return {c: [re.compile(p, re.IGNORECASE) for p in pats] for c, pats in LEADERSHIP_CATEGORIES.items()}


def group_of(skill: str) -> str | None:
    entry = skill_patterns().get(skill)
    return entry[0] if entry else None


def category_of_group(group: str) -> str:
    if group in ARCHITECTURE_GROUPS:
        return "architecture"
    if group in TOOL_GROUPS:
        return "tools"
    return "technical"
