# Bhavesh Chaudhary

**Aspiring Full Stack Developer — Python · SQL · Vue.js · ELK · Docker**

Haldwani, Uttarakhand | +91 90275 54259 | bhavesh.chaudhary1608@gmail.com

## SUMMARY

Final-year B.Tech CSE student (2027). Built **Sentinel** — an AI-usage monitoring & DLP system for managed work devices — end to end: FastAPI REST backend, async Celery pipeline, NLP data classification, Chrome MV3 extension, React dashboard, full Docker orchestration, and a 37-test CI-ready pytest suite. Also built a multi-tenant SaaS ticket tracker on MS SQL Server with BDD tests and ELK monitoring. Comfortable owning code across its whole lifecycle: development, testing, deployment, iteration.

## TECHNICAL SKILLS

| Area | Skills |
|---|---|
| Languages | Python, SQL, TypeScript, JavaScript, C (C# fundamentals) |
| Frontend | Vue 3 (Pinia, Vue Router, Vite), React (Vite), HTML/CSS |
| Backend & APIs | FastAPI, REST API design, JWT auth, Pydantic, Celery, Redis |
| Databases | PostgreSQL, MS SQL Server (multi-tenant design, Row-Level Security), MySQL |
| Testing & BDD | pytest, pytest-bdd (Cucumber/Gherkin), API integration tests |
| Monitoring (ELK) | Elasticsearch, Logstash, Kibana; structured JSON logging |
| AI/NLP | spaCy, Microsoft Presidio, sentence-transformers |
| DevOps | Docker, Docker Compose, GitHub Actions (CI/CD), nginx, Alembic |
| Practices | Agile/Scrum, Git, linting (ruff, vue-tsc), code review |

## PROJECTS

### Sentinel — AI Usage Monitoring & Data Loss Prevention System
*Python · FastAPI · Celery/Redis · PostgreSQL · React · Chrome Extension (MV3) · Docker · spaCy/Presidio NLP · pytest*

- **Full-stack ownership:** designed and built the entire system solo — FastAPI REST API, async Celery workers on Redis, PostgreSQL via SQLModel with Alembic migrations, 7-service Docker Compose stack.
- **AI data-loss detection:** Chrome MV3 extension captures AI prompts on ChatGPT, Gemini, Claude & Copilot via shadow-DOM-piercing content scripts; a multi-tier NLP pipeline (regex → Presidio PII → sentence-transformer semantic scoring) detects credentials, PII, financial data, and source-code leakage.
- **Policy engine & alerting:** prioritized DLP rules (block / warn / log) evaluated pre-flight with risk scores; real-time WebSocket alert fan-out to an admin React dashboard with usage analytics and risk trends.
- **Consent-first & privacy-aware:** explicit consent flow, JWT + RBAC, configurable storage modes (verbatim vs. flagged-only), prompts-only capture, automated retention purging, immutable audit log.
- **Testing & CI:** 37-test pytest suite covering auth, capture, classification, policy, and retention; containerized runs make the pipeline CI-ready on every push.

### Ticket Tracker — Multi-Tenant SaaS Task & Ticket Tracker
*Python · FastAPI · Vue 3 (TypeScript, Pinia) · MS SQL Server · ELK Stack · Docker · GitHub Actions*

- **Multi-tenant architecture:** shared-schema design on MS SQL Server where every table carries `tenant_id`; each query is tenant-scoped from JWT claims at a single choke point, with Row-Level Security as defense in depth.
- **REST API:** FastAPI service for signup/login (JWT + PBKDF2), projects, and tickets with server-side workflow validation; cross-tenant access returns 404 so resource existence is never leaked.
- **BDD testing:** 56 tests including Cucumber/Gherkin scenarios (pytest-bdd) verifying tenant isolation, kanban workflow, and dashboard stats.
- **ELK monitoring:** every request emits structured JSON (`tenant_id`, `request_id`, `status`, `duration_ms`) shipped to Logstash → Elasticsearch → Kibana dashboards for traffic, error rates, and slow endpoints.
- **CI/CD:** full 6-service stack orchestrated with Docker Compose; GitHub Actions pipeline runs ruff lint → backend tests → vue-tsc typecheck → Vite build → Docker builds on every push.

## EDUCATION

**B.Tech — Computer Science & Engineering** | 2023 – 2027
Graphic Era Hill University, Bhimtal · CGPA: 7.8 / 10
Relevant coursework: DBMS, Web Technologies, Software Engineering, Operating Systems, Computer Networks
