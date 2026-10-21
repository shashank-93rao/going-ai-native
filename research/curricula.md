# Curricula survey: existing AI engineering / agents / evals courses

Researched 2026-10-19. Purpose: compare what existing courses teach against our draft topic list (`00-draft-topics.md`) and find gaps.

**Sourcing conventions**
- Lesson and module titles were taken from the live curriculum pages unless a different source is named.
- **[unverified]** marks content that comes from third-party mirrors, search snippets, or inference from folder or file names.
- **Udemy blocked every fetch.** Direct page loads, enterprise subdomains, and the public API all returned HTTP 403. For Udemy courses I used the ctgoodjobs.hk mirror (it shows section titles but not lecture titles), the instructors' public GitHub repos (notebook headings), and search snippets.

---

## 1. Udacity: Agentic AI Nanodegree (nd900)

- **URL:** https://www.udacity.com/course/agentic-ai--nd900
- **Provider:** Udacity
- **Size:** 4 courses, 67 lessons, 4 projects, about 53 hours.
- **Prerequisites:** Basic prompting, basic Python, the OpenAI API, and Azure basics.
- **Stack:** OpenAI SDK/API, Pydantic, SQLAlchemy/SQLite, ChromaDB, the Tavily API, Python threading, and MCP. The page names no LangGraph or CrewAI, so the course is effectively framework-free.

### Course 1: Prompting for Effective LLM Reasoning and Planning (13 hours)
1. Introduction to Prompting for Effective LLM Reasoning and Planning
2. The Role of Prompting in Agentic AI with Python and OpenAI
3. Role-Based Prompting, then Implementing Role-Based Prompting with Python
4. Chain-of-Thought and ReACT Prompting, then Applying CoT and ReACT Prompting with Python
5. Prompt Instruction Refinement: improve a prompt iteratively by adjusting role, task, context, examples, and output format. Followed by Applying Prompt Instruction Refinement with Python.
6. Chaining Prompts for Agentic Reasoning, then Chaining Prompts with Python
7. **LLM Feedback Loops:** an agent refines its output over repeated cycles using feedback from its actions. Followed by **Implementing LLM Feedback Loops with Python**, in which the AI writes Python code, runs it against unit tests, and uses the failures to debug itself.
8. Course review

**Project:** AgentsVille Trip Planner. A multi-agent travel assistant that uses CoT and ReAct to plan and coordinate itineraries.

### Course 2: Agentic Workflows (14 hours)
1. Introduction to Agentic Workflows; Understanding Agentic Workflows
2. Agentic Workflow Modeling: diagram workflows using agent types as building blocks. Followed by Implementing Agentic Workflow Modeling.
3. Agentic Workflow Implementation
4. Patterns, each with a Python implementation lesson: Prompt Chaining, Routing, Parallelization, Evaluator-Optimizer, Orchestrator-Workers
5. Course review

**Project:** AI-Powered Agentic Workflow for Project Management. Build a reusable library of agent types, then run a multi-step technical project-management workflow with routing and chaining.

### Course 3: Building Agents (11 hours)
1. Introduction; Extending Agents with Tools; Building Agents with Tools in Python
2. Structured Outputs; Implementing Structured Outputs with Pydantic
3. Agent State Management, using state machines to track input, instructions, and tool use. Followed by Implementing Agent State Management with Python.
4. Short-Term Agent Memory; Adding Agent Memory with Python
5. External Tools and APIs; Integrating External Tools and APIs with OpenAI & Python
6. Web Search Agents; Creating Web Search Agents with Python
7. Interacting with Databases; Building Database Agents in Python
8. Agentic RAG; Agentic RAG with Python and ChromaDB
9. Long-Term Agent Memory; Maintaining Long-Term Agent Memory in Python
10. **Agent Evaluation:** task completion, output quality, tool use, and system metrics, assessed through response, step, or trajectory evaluation. Followed by **Evaluating Agents with Python** (test cases and multiple evaluation methods).
11. Conclusion

**Project:** UdaPlay. A stateful research agent for the video game industry that combines web search, tools, and RAG.

### Course 4: Multi-Agent Systems (14 hours)
1. Introduction; Designing Multi-Agent Architecture; Creating Multi-Agent Designs
2. Multi-Agent Architecture with Python (concept and implementation)
3. Orchestrating Agent Activities; Implementing Agent Orchestration
4. Routing and Data Flow in Agentic Systems (concept and implementation)
5. State Management in Multi-Agent Systems (concept and implementation)
6. Multi-Agent Orchestration and State Coordination (concept and implementation): keep shared state synchronized
7. Multi-Agent RAG (concept and implementation)
8. Course review

**Project:** The Beaver's Choice Paper Company Sales Team. A multi-agent sales system built on shared state, routing, and orchestration.

### Worth adapting
- **The code→unit-test→self-debug feedback loop (Course 1).** This is the simplest generate→verify→fix loop. Use it as the first exercise in 06b.
- **Implement each Anthropic workflow pattern in raw Python, one lesson per pattern (Course 2).** This is a good skeleton for module 06 before frameworks appear in 06c.
- **Response, step, and trajectory levels of agent evaluation.** This maps cleanly onto the levels of module 10.
- **Weakness:** evaluation gets 2 of 67 lessons, and there is no LLM-judge calibration, hill-climbing, or production observability. This confirms that our eval-heavy angle is differentiated.

---

## 2. Udemy: top courses

Rankings use enrollment and rating figures from mirrors and from travis.media's "Top 10 best-selling AI courses on Udemy (2026)". None of the curricula could be fetched from Udemy itself (HTTP 403).

### 2a. Ed Donner: AI Engineer Core Track: LLM Engineering, RAG, QLoRA, Agents
- **URL:** https://www.udemy.com/course/llm-engineering-master-ai-and-large-language-models/ (blocked). Section titles come from the ctgoodjobs mirror. Labs come from https://github.com/ed-donner/llm_engineering.
- **Stats:** About 171k students, 4.7 rating, 361 lectures. travis.media reports 300k+ students.
- **Sections (verbatim from the mirror):**
  1. Week 1: Build Your First LLM Product: Exploring Top Models (website brochure generator; Ollama on day 1)
  2. Week 2: Build a Multi-Modal Chatbot: LLMs, Gradio UI, and Agents (an airline support agent with function calling)
  3. Week 3: Open-Source Gen AI: Automated Solutions with HuggingFace (meeting minutes from audio, on Colab GPU)
  4. Week 4: LLM Showdown: Evaluating Models for Code Gen & Business Tasks (Python→C++ code-conversion tool)
  5. Week 5: Mastering RAG: Build Advanced Solutions with Vector Embeddings. The repo has `evaluation/` and `evaluator.py` folders, so it includes RAG evaluation **[inferred from repo]**.
  6. Week 6: Fine-tuning Frontier LLMs with LoRA/QLoRA (price predictor, Capstone Part A)
  7. Week 7: Fine-tuned open-source model competes with frontier models on price prediction (Capstone Part B)
  8. Week 8: Build an autonomous multi-agent system collaborating with models ("The Price is Right" deal-alert agent framework, Capstone Part C)
- **Projects:** Brochure generator, multimodal airline support agent, meeting-minutes generator, Python→C++ optimizer, RAG knowledge worker, price predictor (frontier, then fine-tuned), and an autonomous deal-finding multi-agent system.

### 2b. Ed Donner: AI Engineer Agentic Track: The Complete Agent & MCP Course
- **URL:** https://www.udemy.com/course/the-complete-agentic-ai-engineering-course/ (blocked). The Udemy sections are only "Week 1 … Week 6 – MCP" (129 lectures, 16h49m, about 165k students, 4.7). The detail below comes from notebook headings in https://github.com/ed-donner/agents, which the README calls a "refreshed version from Summer 2026".
- **Week 1, Foundations:** lab 1 (first API call); lab 2 (calling multiple providers: OpenAI, Ollama, Grok…); lab 3 (refresher concepts, then tools: a JSON tool description and a new `chat()` loop); lab 4, the first big project, a **Digital Twin** career agent with Pushover notifications and deployment.
- **Week 2, OpenAI Agents SDK:**
  - Day 1: a simple "Agent" and **"Agent Loop"**, adding a tool, adding memory, adding observability with a trace.
  - Day 2: orchestration by code vs orchestration by LLMs (an email sales-development agent).
  - Day 3: any model through OpenAI-compatible endpoints, structured outputs, **guardrails**, and an optional sandbox agents section.
  - Day 4: **Deep Research** with 4 agents (search, planner, writer, email) using hosted web-search tools.
- **Week 3, CrewAI:** CrewAI 1.14.4 projects, plus installing CrewAI "skills" for coding agents. The project list wasn't visible.
- **Week 4, LangChain/LangGraph:**
  - Lab 1: "the four levels of abstraction" (building blocks, streaming, any provider).
  - Lab 3: `create_agent` (tools, "the reveal: it is a LangGraph graph", memory, structured output, middleware).
  - Lab 4: **Deep Agents** (planning research agent, sub-agents, Agent Skills).
  - Lab 5: the **Sidekick**, a personal co-worker agent built in three steps: no evaluator, then human-in-the-loop via middleware, then the full Sidekick with an evaluator. It browses through Playwright.
- **Week 5, Agent frameworks:** the same worker built five times across Google ADK + A2A, Strands + Pydantic AI, Microsoft Agent Framework + Agno, and Mastra (TypeScript). **Day 5 is Project 7, "The Agent Loop".**
  - An ADK orchestrator launches the five workers in parallel against a shared task board.
  - A short-lived QA agent tests each built game in a real browser through Playwright MCP.
  - Broken work goes back to its builder, with at most one fix attempt.
  - Hung workers are killed by a time limit.
  - The lab's framing: "The inner loop … (read the board, plan steps, work them, check them off) … becomes an outer loop, and an agent runs it."
- **Week 6, MCP:**
  - Lab 1: MCP inside the Agents SDK, with Node and Playwright servers.
  - Lab 2: writing your own MCP server and client **[inferred]**.
  - Lab 3: **"Context Engineering with MCP"** (long-term memory, web search, agentic RAG, integrations).
  - Lab 5: the capstone trading-floor app, improved with observability (a custom tracer), **"Evaluation & Feedback: a strategy that improves itself"**, and a production frontend.
- **Worth adapting:**
  - The "same agent, five frameworks" week maps directly onto our 06c goal of building the same agent with the raw SDK and with LangGraph. We could extend it to two or three frameworks.
  - The Day 5 orchestrator is a concrete multi-agent outer loop. It has a verifier (a browser QA agent), a bounded retry (one fix), and timeouts. That is a good 06b exercise.
  - "Orchestration by code vs by LLM" is a good contrast for 06 (workflows vs agents).

### 2c. Eden Marco: LangChain: Develop AI Agents with LangChain & LangGraph
- **URL:** Udemy (blocked). Data comes from the ctgoodjobs mirror: about 146k students, 4.6 rating (43k ratings), 18h35m, 163 lectures, updated 1/2026.
- **Sections (verbatim):**
  1. Introduction
  2. The GIST of LangChain: your "Hello World" chain
  3. The GIST of AI Agents
  4. The Original LangChain ReAct Agent
  5. Diving Deep Into ReAct Agents: what is the magic?
  6. Function Calling
  7. The GIST of RAG: Embeddings, Vector Databases & Retrieval
  8. Building a documentation assistant (embeddings, vector DBs, retrieval, memory)
  9. Prompt Engineering Theory
  10. Let's Talk About LLM Applications In Production
  - The mirror shows only 10 sections, while the "what you'll learn" list also names MCP, LangGraph, and context engineering. Sections may be truncated **[uncertain]**.
- **Worth adapting:** Section 5 ("what is the magic", which reads the ReAct loop source) matches our 06b goal of agent-loop internals. Reading the framework's own loop source is a good exercise.

### 2d. Eden Marco: LangGraph: Develop LLM powered AI agents with LangGraph
- **Stats:** 4.5 rating (3.7k reviews), 7.5 hours, 73 lectures, intermediate. Covers LangGraph Studio, the LangGraph Cloud API, and LangGraph Cloud (from Class Central and the Udemy topic page).
- **Section list:** not retrievable, since both Udemy and Class Central returned 403 **[gap]**. From memory of earlier versions, it has reflection agents, Reflexion, agentic RAG (corrective and adaptive RAG), and a "structured outputs + LangGraph" section. Treat this as unverified.

### 2e. Mike & James: The Complete Prompt Engineering for AI Bootcamp (2026)
- **Stats:** About 337k students, 4.5 rating (137k ratings), 22h55m, 219 lectures (ctgoodjobs mirror). This appears to be the largest prompt-engineering bestseller.
- **Sections (verbatim):**
  1. Introduction
  2. Five Principles of Prompting
  3. How Does AI Work?
  4. Deep Dive on ChatGPT
  5. Standard Text Model Practices
  6. OpenAI Features & Functionality (coding)
  7. Retrieval, Embeddings and Vector Databases (coding)
  8. Building AI Agents (coding)
  9. Advanced Text Model Techniques (coding)
  10. Deep Dive on LangChain (coding)
  11. Deep Dive on LangGraph (coding)
  12. AI Text Model Projects
  13. Deep Dive on Midjourney v6
  14. Standard Image Model Practices
  15. Advanced Image Generation Techniques
  16. AI Image Model Projects
  17. **Prompt Optimization & Evals**
  18. Agent Architectures (coding)
  19. Deep Dive on Google Veo3
  20. Deep Dive on DALL-E 3
  21. Deep Dive on other AI Models
  22. Conclusion
  - A preview mirror (mejba.me) lists chapters named "Give Clear Direction", "Provide Reference Examples", "Evaluate and Iterate on Quality", and "What Are Tokens and Why They Matter".
- **Worth adapting:** the "five principles of prompting" framing: give direction, specify format, provide examples, evaluate quality, divide labor. These are the principles from the instructors' O'Reilly book **[from memory; unverified on page]**. "Evaluate quality" being a prompting principle supports framing module 02 as specification plus test.

### 2f. Other Udemy entries (stats only)
- **RPATech, Prompt Engineering with ChatGPT Masterclass:** about 110k students, 4.5 rating, 4 hours. Sections: Course Overview, Intro to ChatGPT, Sign-up/UI, ChatGPT Go, Intro to Prompts, Prompt Types and Examples, and frameworks (CRISPE, RICE, AAA). It also mentions "context engineering". It is aimed at non-engineers and is out of scope for us.
- **The AI Engineer Course 2026: Complete AI Engineer Bootcamp:** 100k+ students, 4.6 rating, about 30 hours. Covers Python, NLP, transformers, LangChain, RAG, Pinecone, prompt engineering, and agents.
- **Ryan Ahmed, LLM Engineering, RAG, & AI Agents Masterclass:** 14 projects using LangGraph, CrewAI, AutoGen, n8n, MCP, and the OpenAI Agents SDK.
- **MCP courses** are small. The largest is "MCP Bootcamp: Build, Deploy & Secure" with about 8k students.
- **"Loop Engineering" and "Loop Engineering Crash Course"** (52 minutes, 14 lectures, updated 8/2026). Their marketing outline lists "five ways a loop should be able to exit", memory design, and guardrails **[snippet only; low ratings count]**.

---

## 3. LangChain Academy (every course listed)

- **URL:** https://academy.langchain.com/collections
- **Collections:** All Courses, plus **Build / Test / Deploy / Monitor**. These follow LangChain's "Agent Development Lifecycle (ADLC)".
- **Catalog size:** The catalog paginates across 4 pages with 19 items.
- **"LangChain v1 essentials":** no course has that name. The v1 `create_agent` material is in "Quickstart: LangChain Essentials" and "Introduction to LangChain".
- **Certification:** there is a certification track, the **LangChain Certified Agent Engineer (LCAE)**. Its prerequisite bundle is: Intro to LangChain (Build), Intro to Deep Agents (Build), Building Reliable Agents with LangSmith (Test), Intro to LangSmith Deployment (Deploy), and Monitoring Production Agents (Monitor). There is also an LCAE Practice Exam.

### 3.1 Introduction to LangGraph (Python): https://academy.langchain.com/courses/intro-to-langgraph
- **M0:** Overview and setup
- **M1 Introduction:** Motivation; Simple Graph; LangSmith Studio; Chain; Router; Agent; Agent with Memory; [Optional] Intro to Deployment
- **M2 State and Memory:** State Schema; State Reducers; Multiple Schemas; Trim and Filter Messages; Chatbot with Summarizing Messages and Memory; Chatbot with Summarizing Messages and External Memory
- **M3 UX and Human-in-the-Loop:** Streaming; Breakpoints; Editing State and Human Feedback; Dynamic Breakpoints; **Time Travel**
- **M4 Building Your Assistant:** Parallelization; Sub-graphs; Map-reduce; Research Assistant
- **M5 Long-Term Memory:** Short vs Long-Term Memory; LangGraph Store; Memory Schema + Profile; Memory Schema + Collection; Build an Agent with Long-Term Memory
- **M6 Deployment:** Deployment Concepts; Creating a Deployment; Connecting to a Deployment; **Double Texting**; Assistants

### 3.2 Quickstart: LangGraph Essentials (Python; a TypeScript twin exists): https://academy.langchain.com/courses/langgraph-essentials-python
- **Lessons:** Nodes; Edges; Conditional Edges; Memory; Interrupt / Human in the Loop; Application (an email workflow)

### 3.3 Quickstart: LangChain Essentials (Python; a TypeScript twin exists): https://academy.langchain.com/courses/langchain-essentials-python
- **Lessons:** Create Agent; Models and Messages; Streaming; Tools; Tools with MCP; Memory; Structured Output; Dynamic Prompt; Human in the Loop

### 3.4 Introduction to LangChain (Python): https://academy.langchain.com/courses/foundation-introduction-to-langchain-python
- **M1 Create Agent:** Foundational Models; Tools; Short-Term Memory; Multimodal Messages; Personal Chef (project)
- **M2 Advanced Agent:** MCP; Context and State; Multi-Agent Systems; Wedding Planner (project)
- **M3 Production-Ready Agent:** What is Middleware?; Managing Long Conversations; Human In The Loop; Dynamic Agents; Email Assistant (project); Agent Chat UI (bonus)

### 3.5 Introduction to Deep Agents: https://academy.langchain.com/courses/foundation-introduction-to-deepagents
"Build long-running agents with Deep Agents, an open-source agent harness."
- **M1 Building a Deep Agent:** Overview; Running a Deep Agent; Models; The System Prompt; Tools; MCP; Messages, Threads, and Checkpointers; HITL; Test Your Skills
- **M2 Execution Environment:** The Deep Agent Environment; Filesystem Backends; **Sandboxes and LocalShell**; Interpreter
- **M3 Context Management:** **Summarization and Offload**; Skills; Memory
- **M4 Delegation:** Delegation; Building a Subagent Team; Dynamic Subagents
- **M5 Putting It All Together:** Project Overview; Local Deployment; The Sales Assistant; **Asynchronous Subagents**; The Advanced Sales Assistant
- **M6 Managed Deep Agents:** What is MDA?; MDA Project Structure

### 3.6 dcode Essentials (Deep Agents Code, a coding agent): https://academy.langchain.com/courses/dcode-essentials
- **Lessons:** Welcome to dcode; dcode Essentials; Goals; Skills, MCP, Plugins, and Marketplaces; Configuring Subagents; dcode for Enterprise

### 3.7 Project: Ambient Agents with LangGraph: https://academy.langchain.com/courses/ambient-agents
- **Modules:** M1 LangGraph 101; M2 Building Agents; M3 **Agent Evaluations**; M4 Human-in-the-Loop; M5 Memory; M6 Deployment. Each module is a single long lesson. The page claims 28 lessons, but the curriculum shows 24 items.
- **Project:** an email assistant that triages and acts on incoming mail. It is "ambient" because it runs on events rather than chat.

### 3.8 Project: Deep Research with LangGraph: https://academy.langchain.com/courses/deep-research-with-langgraph
- **Modules:** M1 Overview; M2 **Scope** (scoping or clarifying the user request); M3 Research Agent; M4 Research Agent with MCP; M5 Research Supervisor; M6 Multi-Agent Research System. Evaluated with LangSmith.

### 3.9 Introduction to Agent Observability & Evaluations (older "Intro to LangSmith"): https://academy.langchain.com/courses/intro-to-langsmith
- **M1 Visibility While Building with Tracing:** Tracing Basics; Types of Runs; Alternative Ways to Trace; Conversational Threads
- **M2 Testing and Evaluation:** Datasets; Evaluators; Experiments; Analyzing Experiment Results; [Optional] **Pairwise Experiments**; [Optional] **Summary Evaluators**
- **M3 Prompt Engineering:** Playground; Prompt Hub; Prompt Engineering Lifecycle; Polly (an AI prompt assistant)
- **M4 Collecting Human Feedback:** User Feedback; **Annotation Queues**
- **M5 Production Observability:** Filtering; Online Evaluation; Automations; Monitoring; Custom Dashboards

### 3.10 Quickstart: LangSmith Essentials: https://academy.langchain.com/courses/quickstart-langsmith-essentials
- **M1 Agent Observability:** What is Tracing?; Debugging with Studio; Capstone
- **M2 Testing Your Agent Pre-Production:** Datasets and Offline Evals; Experiments; Capstone
- **M3 Running Agents in Production:** Deployments
- **M4 Monitoring in Production:** Online Evaluators and Automations; Annotation Queues; Insights; Dashboards; Capstone
- **M5 Closing the Loop:** Closing the Loop; Automating the ADLC with LangSmith Engine; Conclusion

### 3.11 Building Reliable Agents with LangSmith (LCAE "Test"): https://academy.langchain.com/courses/building-reliable-agents
"From first run to production-ready through repeated improvement cycles."
- **M0:** Intro: The Agent Development Lifecycle; Glossary
- **M1 Observation:** Observability; Tracing with LangSmith; Analyzing your Agent
- **M2 Evaluation:** Evaluating Agents; Creating Datasets; Running Experiments; Eval 1, Code-based; Eval 2, LLM-as-Judge; Eval 3, Pairwise
- **M3 Moving Towards Production:** Moving Towards Production; Insights Agent; Online Evals; Automations

### 3.12 Autonomous Agent Improvement with LangSmith Engine: https://academy.langchain.com/courses/langsmith-engine
- **Lessons:** What is the ADLC?; Creating a Recruiting Agent; Setting Up Engine; Build: Engine Proposes a Fix; Test: Testing Engine's Fix; Deploy: Shipping the Fix; Monitor: Monitoring in Production; Homework: Expanding the Recruiting Agent
- **What it automates:** the hill-climbing loop. It finds errors in production traces, proposes fixes, validates them with experiments, and monitors for regressions.

### 3.13 Monitoring Production Agents (LCAE "Monitor"): https://academy.langchain.com/courses/production-monitoring
- **M1 Monitoring Cost:** Token and Cost Breakdowns; Tracking Costs; Viewing Costs; Lab; Quiz
- **M2 Monitoring Product Analytics:** Analyze Trends with Insights; Lab; Quiz
- **M3 Monitoring Quality:** Monitoring Latency and Errors; **Monitoring User Sentiment**; **A/B Testing**; Lab; Quiz
- **M4 Monitoring Security:** Monitoring Security; Setting Up Alerts; Lab; Quiz
- **Capstone Project** plus quiz

### 3.14 Introduction to LangSmith Deployment (LCAE "Deploy"): https://academy.langchain.com/courses/langsmith-deployment
- **M1 Deploy Your Agent:** The Agent; Deploy; Use the Tutor
- **M2 Connecting:** Connecting; Assistants; Connecting the UI; Custom Routes
- **M3:** Deployment UI walkthrough
- **M4 Memory:** Memory in LangGraph; Accessing Storage; Memory in Deep Agents
- **M5 Multi-Tenant Auth:** Intro to Auth; Authentication; Authorization; Auth Provider; Auth on Tutor
- **M6 Deep Agent Deploy:** deepagents-cli no-code deploy; Exercise; Bring Your Own UI

### 3.15 LangSmith Fleet (no-code agent builder): https://academy.langchain.com/courses/quickstart-agent-builder
- **Lessons:** Building An Agent; Human-In-The-Loop; What Can Agents Do?; Skills; MCP; **Ambient Agents**; Sub-Agents; **Computer Use (Sandboxes)**; Templates

### 3.16 LCAE Practice Exam / LCAE Prerequisite bundle
- These are listed above. Neither has its own content.

### Worth adapting (LangChain Academy overall)
- **ADLC framing (Build → Test → Deploy → Monitor → close the loop).** This is a clean spine for modules 07–12 and the capstone.
- **Time Travel and checkpointers.** Replaying and forking an agent run from a checkpoint is a natural "record/replay" exercise for module 10, and it maps to event sourcing for a distributed-systems engineer.
- **Double Texting.** A user sends a second message while a run is in flight, and you choose reject, enqueue, interrupt, or rollback. This is a concurrency-control problem our learner will recognize. Use it in 06c.
- **Deep Agents M2–M4.** Filesystem backends, sandboxes, summarization and offload, and async subagents form a concrete "harness" anatomy for 03, 05, and 06b.
- **Ambient Agents project.** An event-triggered agent with evals plus HITL plus memory is a good capstone alternative.
- **Pairwise and summary evaluators, and annotation queues.** These are small eval primitives we currently lack.
- **LangSmith Engine.** Use it as a case study of automated hill-climbing (module 09), and contrast it with doing the loop manually first.

---

## 4. DeepLearning.AI

### 4.1 Agentic AI (Andrew Ng): https://www.deeplearning.ai/courses/agentic-ai/
Intermediate, about 10 hours, 31 videos, 7 code examples, 8 graded items.
- **M1 Intro to Agentic Workflows:** What is agentic AI; **Degrees of autonomy**; Benefits; Applications; **Task decomposition**; **Evaluating agentic AI (evals)**; Agentic design patterns; Try the research agent
- **M2 Reflection Design Pattern:** Reflection to improve outputs; Why not direct generation; Chart generation workflow (lab); **Evaluating the impact of reflection**; **Using external feedback**; Improving SQL generation with reflection (lab); graded lab
- **M3 Tool use:** What are tools; Creating a tool; Tool syntax; Functions→tools (lab); Email assistant workflow (lab); **Code execution**; MCP; graded lab
- **M4 Practical Tips for Building Agentic AI:** Evaluations (evals); **Error analysis and prioritizing next steps**; More error-analysis examples; **Component-level evaluations**; Adding a component-level eval to the research workflow (lab); How to address problems you identify; **Latency, cost optimization**; **Development process summary**
- **M5 Patterns for Highly Autonomous Agents:** **Planning workflows**; Creating and executing LLM plans; **Planning with code execution**; Customer service agent (lab); Multi-agentic workflows; Market research team (lab); Communication patterns for multi-agent systems; graded assignment
- **Worth adapting:**
  - "Evaluating the impact of reflection" measures whether a loop actually helps rather than assuming it does. This is a good 06b/09 exercise.
  - Error analysis → "prioritize next steps" → component-level eval is the core loop of module 09.
  - "Planning with code execution" (the plan is written as code) is a pattern we don't name yet.

### 4.2 Evaluating AI Agents (with Arize; Gilhuly & Khan): https://www.deeplearning.ai/short-courses/evaluating-ai-agents/
- **Lessons:** Evaluation in the time of LLMs; Decomposing agents; Lab 1 Building your agent (router, skills, memory); Tracing agents; Lab 2 Tracing; Adding router and skill evaluations; Lab 3 (test cases built from traces; code-based and LLM-judge evals per component); Adding trajectory evaluations; Lab 4 (a **convergence score**, which checks whether the agent answers in an efficient number of steps); Adding structure to your evaluations; Lab 5 (structured experiments varying prompt, model, or agent logic); Improving your LLM-as-a-judge; Monitoring agents
- **Worth adapting:** the convergence score is a concrete trajectory-efficiency metric for module 10. Also adopt per-component evals (router accuracy vs skill quality).

### 4.3 AI Agents in LangGraph (Harrison Chase, Rotem Weiss): https://www.deeplearning.ai/short-courses/ai-agents-in-langgraph/
- **Lessons:** Build an Agent from Scratch; LangGraph Components; Agentic Search Tools; Persistence and Streaming; Human in the loop; Essay Writer; LangChain Resources
- **Worth adapting:** the same "from scratch, then LangGraph" structure our 06c already plans. This validates it.

### 4.4 Long-Term Agentic Memory with LangGraph (Harrison Chase): https://www.deeplearning.ai/short-courses/long-term-agentic-memory-with-langgraph/
- **Lessons:** Intro to Agent Memory; Baseline Email Assistant; plus **Semantic** memory; plus **Episodic** memory; plus **Procedural** memory (system prompt refined from feedback)
- **Worth adapting:** the semantic, episodic, and procedural memory taxonomy for module 03. Procedural memory is a self-editing prompt, which is a mild form of hill-climbing.

### 4.5 MCP: Build Rich-Context AI Apps with Anthropic (Elie Schoppik): https://www.deeplearning.ai/short-courses/mcp-build-rich-context-ai-apps-with-anthropic/
- **Lessons:** Why MCP; MCP Architecture; Chatbot Example; Creating an MCP Server (tested with MCP Inspector); Creating an MCP Client; Connecting to Reference Servers (filesystem, fetch); Adding Prompt and Resource Features; Configuring Servers for Claude Desktop; Creating and Deploying Remote Servers; Conclusion (roadmap: registry, discovery, auth)

### 4.6 Claude Code: A Highly Agentic Coding Assistant (Elie Schoppik): https://www.deeplearning.ai/short-courses/claude-code-a-highly-agentic-coding-assistant/
- **Lessons:** What is Claude Code; Setup & Codebase Understanding (a RAG chatbot repo); Adding Features (planning and thinking modes); Testing, Error Debugging and Code Refactoring; **Adding Multiple Features Simultaneously (git worktrees)**; Exploring GitHub Integration & **Hooks**; Refactoring a Jupyter Notebook & Creating a Dashboard; Creating a Web App from a Figma Mockup (Figma and Playwright MCP); Prompts & Summaries

### 4.7 Agent Skills with Anthropic (Elie Schoppik): https://www.deeplearning.ai/short-courses/agent-skills-with-anthropic/
- **Lessons:** Why Use Skills I & II; **Skills vs Tools, MCP, and Subagents**; Exploring Pre-Built Skills; Creating Custom Skills; Skills with the Claude API; Skills with Claude Code; Skills with the Claude Agent SDK

### 4.8 Spec-Driven Development with Coding Agents (Paul Everitt, JetBrains): https://www.deeplearning.ai/short-courses/spec-driven-development-with-coding-agents/
- **Lessons:** Why spec-driven development?; Workflow overview; **Creating the constitution** (mission, tech stack, roadmap); Feature specification; Feature implementation; **Feature validation**; **Project replanning**; The second feature phase; The MVP; **Legacy support** (specs from existing docs); Build your own workflow (packaged as an agent skill); **Agent replaceability**
- **Worth adapting:** constitution → spec → implement → validate → replan is a concrete loop for module 04/14. The legacy-codebase lesson suits experienced engineers.

### 4.9 Safe and Reliable AI via Guardrails (Shreya Rajpal, GuardrailsAI): https://www.deeplearning.ai/short-courses/safe-and-reliable-ai-via-guardrails/
- **Lessons:** Failure modes in RAG apps; What are guardrails; Building your first guardrail; **Checking for hallucinations with NLI**; Using the hallucination guardrail in a chatbot; Keeping a chatbot on topic; Ensuring no PII is leaked; Preventing competitor mentions

### 4.10 Automated Testing for LLMOps (Rob Zuber, CircleCI, Jan 2024): https://www.deeplearning.ai/short-courses/automated-testing-llmops/
- **Lessons:** Intro to CI; Overview of Automated Evals; Automating Model-Graded Evals; Comprehensive Testing Framework; (optional) the CircleCI config
- **Worth adapting:** a cheap eval suite per commit and a fuller suite pre-release. This is a tiered CI pattern, which Hamel's L6 also teaches.

### 4.11 Multi AI Agent Systems with crewAI (João Moura): https://www.deeplearning.ai/short-courses/multi-ai-agent-systems-with-crewai/
- **Lessons:** AI Agents; Research and write an article; Key elements of AI agents; Multi-agent customer support; **Mental framework for agent creation**; Key elements of agent tools; Customer outreach; Key elements of well-defined tasks; Event planning; Multi-agent collaboration; Financial analysis; Tailor job applications

### 4.12 Others in the catalog (titles only, not drilled into)
Build AI Apps with MCP Server: Working with Box Files; Agentic Knowledge Graph Construction; Building AI Assistants with On-Device Memory; Event-Driven Agentic Document Workflows (LlamaIndex). No DL.AI course title mentions "context engineering" or "observability".

---

## 5. Hugging Face Agents Course

- **URL:** https://huggingface.co/learn/agents-course. The unit and page list comes from the repo's `units/en/_toctree.yml`.
- **Unit 0, Welcome:** Onboarding; Discord 101; Live 1 (how the course works)
- **Unit 1, Introduction to Agents:** What is an Agent?; What are LLMs?; Messages and Special Tokens; What are Tools?; **Understanding Agents through the Thought-Action-Observation Cycle**; Thought / Internal Reasoning and ReAct; Actions; Observe (integrating feedback to reflect and adapt); **Dummy Agent Library**; Let's Create Our First Agent Using smolagents; quizzes
- **Unit 2.1, smolagents:** Why use smolagents; **Building Agents That Use Code**; **Writing actions as code snippets or JSON blobs**; Tools; Retrieval Agents; Multi-Agent Systems; Vision and Browser agents
- **Unit 2.2, LlamaIndex:** LlamaHub; Components; Tools; Agents; Agentic Workflows
- **Unit 2.3, LangGraph:** What is LangGraph; Building Blocks; First LangGraph; Document Analysis Graph
- **Unit 3, Agentic RAG use case:** Agentic RAG; RAG tool for guest stories; Building and integrating tools; Creating your Gala agent
- **Unit 4, Final Project: Create, Test, and Certify Your Agent:** What is **GAIA**?; The Final Hands-On (scored on a GAIA subset with a student leaderboard); Certificate; What Should You Learn Now?
- **Bonus 1, Fine-tuning an LLM for function-calling:** What is function calling; fine-tune your model
- **Bonus 2, Agent Observability and Evaluation:** What is observability and evaluation; Monitoring and evaluating agents
- **Bonus 3, Agents in Games with Pokémon:** a Pokémon battle agent
- **Worth adapting:**
  - The "dummy agent library" builds an agent loop from raw text completion with no tool-calling API, so learners see stop sequences and parsing. This is ideal for 06b internals.
  - Code-actions vs JSON tool calls is a design axis we don't cover.
  - Scoring against a public benchmark (GAIA) on a leaderboard is a hill-climbing target with an external, unhackable grader.

---

## 6. Hamel Husain & Shreya Shankar: AI Evals for Engineers & PMs (Maven)

- **URL:** https://maven.com/parlance-labs/evals. The full syllabus is a Google Doc linked from the page (https://docs.google.com/document/d/1KSUlzN-C8z1q_gHduCi6eKgCzlHVV6u3dT0aypqi_YI).
- **Format:** Eight weeks, $4,200, 9 live lectures plus a bonus, a 200+ page course reader, and 6 optional coding homeworks. The next cohort runs Oct 10 – Nov 21, 2026.
- **Thread through the course:** learners build a support agent and evaluate it end to end.
- **Module 1, Building Agents:**
  - **L1, Foundations:** write a **SPEC.md** (scope, roles, tool contracts, **risk tiers**, escalation). Covers the **"Three Gulfs"** (comprehension, specification, generalization), mapped to Analyze, Measure, and Improve. Build the support agent on the OpenAI Agents SDK with **permissions enforced in code**.
  - **L2, Designing for Evaluability:** instrument before real users arrive. Design a **trace data model** (nested spans, model and tool calls, permission denials, **prompt hashes**). Run Langfuse and ClickHouse self-hosted.
  - **L3, Synthetic Data & Scenarios:** build a fictional commerce world with deterministic users and orders plus `facts.yaml`. Write a synthetic-data skill that generates about 500 support and 150 analyst scenarios. Produce a smoke report.
- **Module 2, Error Analysis:**
  - **L4, Finding Failures:** why "let the agent evaluate everything" fails. Build a review loop and interface. **Open coding** (read whole traces, note the *first* failure). **Axial coding** into binary failure modes, then check for saturation. Compare against published taxonomies only after building your own.
  - **L5, Measuring with Evaluators:** one binary evaluator per failure mode, using code for objective checks and a judge only where interpretation is needed. Covers judge prompts, **train/dev/test splits**, **TPR/TNR reporting**, **freeze-and-read-test-once**, and **prevalence estimates with bootstrap CIs**. Applies the same discipline to retrieval, grounding, and handoffs.
  - **Homework:** label at least 60 traces and build a taxonomy of 5–8 binary failure modes.
- **Module 3, CI/CD (L6):**
  - Failures become test cases: input, expected result, initial state.
  - Mechanical failures become code assertions, and subjective failures become pinned judge checks.
  - **Cost tiers:** deterministic checks, then mocked integration tests, then full agent evals.
  - **pass^k for reliability vs pass@k for capability.**
  - **Reset-and-replay** to measure failure rate.
  - A GitHub Actions gate.
  - Post-deploy monitoring: code checks on all traffic, frozen judges on a sample, and dashboards with **corrected prevalence** and alerts.
- **Module 4, Safety (L7):**
  - Uses the **OWASP Top 10 for Agentic Applications**: goal hijack, tool misuse, privilege abuse, memory or context poisoning.
  - "Prompt injection has no reliable detector, so authorization must hold even when the model is compromised."
  - Live red-teaming with **promptfoo**; successful attacks become failing tests.
  - Input, output, and tool guards; human approval for irreversible actions.
  - A governance record under the **NIST AI RMF**, and the EU AI Act floor.
- **Module 5, Improving Agents:**
  - **L8, Accuracy & Joint Optimization:** an **accuracy-vs-cost frontier** that holds prompt, tools, harness, workload, and suite constant and varies one axis at a time. Route each fix to the **cheapest effective layer: prompt → tool design → harness → model/weights**. Do a manual fix loop before automating with **GEPA or a bounded improve-loop**, and guard against reward hacking. Compare frontier baselines against the optimized variant on the held-out slice.
  - **L9, Cost:** profile the main cost drivers (history growth, retrieval depth, repeated tool schemas). Apply prompt caching, model routing, and **cascades calibrated against labels**. Use a weights track (distillation, SFT, RL) only when prompt search is flat. The **upgrade drill**: keep frontier variants as configs, re-run the suite when a new model ships, redraw the frontier, then decide.
  - **Homework:** fix the top failure mode and freeze a winner. Separately, profile cost, measure caching, calibrate a cascade, and run the upgrade drill across at least 2 configs.
- **Bonus:** evals interview prep.
- **Worth adapting (the strongest source for modules 07–10 and 13):**
  - Start from a SPEC.md with risk tiers.
  - Run open and axial coding on at least 60 traces.
  - Build binary per-failure-mode evaluators with TPR/TNR.
  - Freeze the test slice and read it once.
  - Compute bootstrap CIs on prevalence.
  - Use tiered CI and a reset-and-replay failure-rate measurement.
  - Order fixes from the cheapest layer upward.
  - Draw the accuracy/cost frontier and run the model-upgrade drill.
  - Convert red-team attacks into regression tests.
  - These are almost exactly the exercises our 07/08/09 need.

---

## 7. Other well-regarded courses

### 7.1 Anthropic Academy (Skilljar): https://anthropic.skilljar.com/
- **Catalog:** 23 courses, free. They include Claude Code 101, Claude Code in Action, Building with the Claude API, Intro to MCP, MCP Advanced Topics, Intro to Agent Skills, Intro to Subagents, AI Capabilities and Limitations, and the AI Fluency series.
- **Claude Code in Action**, which is long-running and loop-relevant:
  - **Steer the Work:** Steering Long Sessions
  - **Configure Claude:** A CLAUDE.md That Follows; **Verification Skills**; Permission Modes; Hooks
  - **Automate Repeat Work:** **Routines and Headless**; GitHub Actions and Code Review
  - **Verify and Share:** **Trust It: Verifying Unsupervised Runs**; Plugins
  - The page may have been truncated.
- **Building with the Claude API** (84 lessons):
  - **Accessing the API:** requests, multi-turn, system prompts, temperature, streaming, structured data
  - **Prompt evaluation:** typical eval workflow, generating test datasets, running the eval, model-based grading, code-based grading
  - **Prompt engineering techniques:** clear and direct, specific, XML tags, examples
  - **Tool use:** schemas, message blocks, tool results, multi-turn with tools, multiple tools, fine-grained tool calling, text edit tool, web search tool
  - **RAG and Agentic Search:** chunking, embeddings, BM25, multi-index RAG
  - **Features:** extended thinking, images, PDFs, citations, prompt caching, code execution and the Files API
  - **MCP:** servers, clients, inspector, resources, prompts
  - **Claude Code and computer use**
  - **Agents and workflows:** parallelization, chaining, routing, agents and tools, **environment inspection**, workflows vs agents
- **Introduction to Subagents:** What are subagents; Creating a subagent; Designing effective subagents; Using subagents effectively
- **Worth adapting:**
  - The API course puts evals *before* prompt-engineering techniques. That ordering is right for our 02→07.
  - "Verifying unsupervised runs" and "Routines and headless" belong in 06b.

### 7.2 Steve Kinney: AI Development Setup: https://stevekinney.com/courses/ai-development-setup
The most detailed public treatment of loops found.
- **Foundations:** Towards Systems Thinking; Planning and Task Contracts; Verification and Evidence; **Recovering a Failing Session**; User and Project Instructions; **The Enforcement Ladder**
- **Cache Money:** Prompt Caching and Cost; Managing a Long Session
- **Skills:** Skills; Configuring Skills; Exemplar Skills
- **Subagents:** Subagents; Configuring Subagents; Exemplar Subagents
- **Hooks:** Hooks; Writing Good Hooks; Hooks in Practice
- **Automation:** Dynamic Workflows; Running Workflows; **Goals and Loops**; Goals and Loops in Practice; **Routines and Schedules**; **Where State Lives**
- **Patterns:** Agentic Coding Patterns; Proving It Works; Deciding What to Build; Keeping Context Useful; **Running Unattended Work**; Claude Code and Codex, Together; **The Ralph Loop**; **Sentinels**; **Committee Review**
- **Extensions:** Worktrees; Agent Teams; Agent Communication; Claude Code Mods; and more (the list was truncated)
- **"The Ralph Loop" lesson content:**
  - The loop is framed as a **control loop** with five parts: `measure()` → `pick()` → `run()` (the only part the agent controls) → `accept()` → **governor**.
  - `accept()` runs each attempt in a disposable checkout and rejects it if any veto fires or the score drops.
  - The governor enforces caps on attempts, time, tokens, and spend. It detects stalls (progress means a kept change *and* an improved score), stops after repeated identical failures, honours a stop file, takes resource locks, and keeps per-attempt logs and diffs. A human gate sits before merge.
  - **Oracle ranking:** user-written exit codes > error counts > parity harnesses > green tests > coverage > LLM referees (last).
  - The "done" signal must come from CI, a hook, or a human, never from a file the agent can write.
  - Fail closed when measurement breaks. Typed exit codes: success, fail, blocked, broken.
  - Restrictions are enforced with `--disallowedTools`, not prompt text. Headless flags: `--max-turns`, `--max-budget-usd`, `--output-format json`.
  - Fresh-context Ralph vs a Stop-hook `/goal` loop that accumulates context.
  - Build order: **the oracle first (prove it can fail using known-bad changes)**, then the queue, spend limits, per-iteration logs, and the loop last.
  - The best evidence that loops work comes from file-by-file migrations and coverage campaigns.
- **Worth adapting:** almost wholesale for module 06b. The five-part control-loop decomposition and the oracle-quality ranking are excellent teaching devices for a distributed-systems engineer.

### 7.3 Laracasts: The Ralph Wiggum Technique (16 episodes, updated May 2026): https://laracasts.com/series/the-ralph-wiggum-technique
- **Episodes:**
  1. What Is Ralph?
  2. Improving Our First Ralph Loop (Node wrapper, streaming progress)
  3. What Is A PRD?
  4. Creating A PRD With Our PRD Skill
  5. **Running Ralph In The Background** (screen/tmux)
  6. **Permissions And Sandboxing**
  7. Configuring Hooks (a pre-tool-use model reviewer)
  8. A Word On Auto Mode
  9. Bypassing Permissions Safely
  10. Turning the Script Into a CLI
  11. **Agent Workspaces** (worktrees, copy-on-write)
  12. Tracking PRDs With Linear
  13. Human In The Loop
  14. **Offloading Loops To A Remote Machine**
  15. Experimenting With A Perpetual Loop
  16. Beyond Ralph: Orchestration

### 7.4 Hugo Bowne-Anderson (Maven)
- **Build AI Agents from First Principles:** https://maven.com/hugo-stefan/build-ai-agents-from-first-principles. 4.8 rating from 18 reviews. Agenda:
  1. From LLM call to agent loop
  2. **Harness Engineering** (prompts, tools, context, memory, state, guardrails; use traces to improve the loop)
  3. Agent SDKs: rebuild the loop and see what the SDK handles
  4. MCP and reusable architecture
  - **Project:** a customer-service agent built from scratch.
- **Free session, "Loop Engineering, Without the BS" (Jul 28, 2026):** https://maven.com/p/c6d4f5/loop-engineering-without-the-bs
  - A loop is generate → score → revise → repeat, compared with search, gradient descent, and testing.
  - Covers the **verification matrix** (human vs agentic verification), with Karpathy's "auto research", search ranking, and Bayesian modeling as examples.
  - When a loop justifies its token cost.
  - **How to stop agents grading their own work:** held-out evals, separate access, human labels, and boundaries the agent can't modify.
  - Q&A on SRE and data-engineering uses.
- **Related free sessions:** "Building Effective Agent Harnesses" and "AI Agent Evals: Test What Matters".

### 7.5 Elite AI-Assisted Coding (Eleanor Berger & Isaac Flath, Maven)
- **URL:** https://maven.com/agentic-ventures/ai-coding. $650 self-paced.
- **Full syllabus:** hidden. The visible units are Unit 1 Welcome and Unit 2 "Foundations: Context Engineering & Frictionless Setup".
- **Overview topics:** a portable context stack; spec-driven development (acceptance criteria); parallel background agents (AGENTS.md, plan.md, todos.md); AI across the SDLC (review, PRs, testing, docs, CI/CD); sandboxing, secrets, and large-codebase practice.

### 7.6 Other Maven sessions
- **"Building a Gi-ralph Loop for Software Development":** a free 45-minute session on May 15, 2026 by Amir Feizpour and Joel Fernandes. Covers loop architectures that don't degrade, how models destabilize loops, and when simpler approaches win. https://maven.com/p/0d968a

### 7.7 Full Stack Deep Learning: LLM Bootcamp (Spring 2023, dated): https://fullstackdeeplearning.com/llm-bootcamp/spring-2023/
- **Lectures:** Prompt Engineering; **LLMOps** (TDD and CI for LLMs, prompt management); **UX for Language User Interfaces**; Augmented Language Models (retrieval, tools); Launch an LLM App in One Hour; LLM Foundations; Project walkthrough askFSDL (Modal deploy, Gantry monitoring); What's Next
- **Invited talks:** Training your own LLM; **Harrison Chase on Agents**; Peter Welinder fireside chat
- **Worth adapting:** the **UX for LUIs** lecture. No other course covers agent UX (how humans review, interrupt, and trust agent output).

### 7.8 UC Berkeley: Agentic AI MOOC (Fall 2025): https://agenticai-learning.org/f25
- **Research-level lectures:** LLM Agents Overview (Dubois, OpenAI); Evolution of system design (Jia, NVIDIA); **Post-Training Verifiable Agents**; **Agent Evaluation**; Lessons from Training Agentic Models; Multi-Agent AI (Noam Brown); **Predictable Noise in LLM** (Sida Wang, Meta, on eval variance); AI for science; **Practical Lessons from Deploying Real-World Agents** (Clay Bavor, Sierra); Multi-Agent Systems (Vinyals); Autonomous Agents (Stone); **Agentic AI Safety & Security** (Dawn Song)
- **Project:** the AgentX-AgentBeats competition.
- **Worth adapting:** the "Predictable Noise in LLM" lecture is a primary source for module 09's error bars. The Sierra lecture covers production lessons.

---

## 8. Who covers LOOPS

| Loop type | Who teaches it (and how) |
|---|---|
| **Agent loop internals (model → tool → observe)** | HF Unit 1 (Thought-Action-Observation; a dummy agent library from raw completions). Ed Donner Agentic Week 1 lab 3 and Week 2 Day 1 ("a simple Agent and Agent Loop"). DL.AI *AI Agents in LangGraph* ("Build an agent from scratch"). Eden Marco ("ReAct: what is the magic?"). Hugo Bowne-Anderson ("From LLM call to agent loop"). Anthropic API course (multi-turn conversations with tools). Udacity Course 1 (ReAct). |
| **Generate → verify → fix (self-correcting)** | Udacity "LLM Feedback Loops" (code → unit tests → self-debug). Ng *Agentic AI* M2 (reflection, **with external feedback**, and measuring whether reflection helps). Udacity and Anthropic evaluator-optimizer pattern. Ed Donner Sidekick (evaluator node) and Week 5 Day 5 (QA agent tests, one bounded fix). Steve Kinney "Proving It Works" and "Verification and Evidence". |
| **Eval-driven improvement loop (hill-climbing)** | Hamel/Shreya L8 (manual fix loop, then a GEPA or **bounded improve-loop**, guarding against reward hacking). LangSmith Engine (automated propose-fix → experiment → deploy → monitor). LangSmith Essentials M5 "Closing the Loop". Ng M4 (error analysis → prioritize). Hugo B-A "Loop Engineering" (generate–score–revise; agents mustn't grade their own work). Ed Donner Week 6 Day 5 ("a strategy that improves itself"). |
| **Long-running autonomous loops (Ralph, `/loop`, scheduled)** | **Steve Kinney** (Ralph loop as a control loop with oracle and governor; Goals and Loops; Routines and Schedules; Running Unattended Work; Where State Lives; Sentinels). **Laracasts** Ralph series (background, remote, perpetual loops, workspaces, PRD-driven). **Anthropic Claude Code in Action** (Steering Long Sessions; Routines and Headless; Verifying Unsupervised Runs). LangChain Deep Agents ("long-running agents" harness; summarization and offload; async subagents). Maven Gi-ralph session. Udemy "Loop Engineering" (unverified). |
| **Event-driven or ambient loops** | LangChain Ambient Agents project; LangSmith Fleet "Ambient Agents" lesson; DL.AI Event-Driven Agentic Document Workflows (not drilled). |
| **Stuck or runaway detection, budgets, stop conditions** | Only **Steve Kinney** covers this in depth (stall detection, repeated-failure stop, spend caps, stop file, typed exit codes). Ed Donner covers it lightly (worker time limits, one fix attempt). The Udemy "Loop Engineering" outline mentions "five ways a loop should exit" (unverified). |

**Takeaway:** the large platforms (Udacity, DL.AI, LangChain Academy, Hugging Face, Udemy bestsellers) teach the inner agent loop and the reflection or evaluator-optimizer loop. None of them teaches long-running autonomous loops as engineering: oracle design, governors, state on disk, stall detection, and cost caps. That material exists only in practitioner courses (Kinney, Laracasts, Anthropic Academy, Bowne-Anderson). Our planned 06b is therefore differentiated. Kinney's lesson is the best existing template.

---

## 9. Topic union vs. draft list

Key: **covered (Mxx)** = the draft already has a home for it. **partial** = mentioned but under-specified. **MISSING** = no home in the draft. **out-of-scope** = deliberately excluded, with the reason.

Course abbreviations used in the table:
- UD = Udacity
- ED-C = Ed Donner Core Track
- ED-A = Ed Donner Agentic Track
- EM = Eden Marco
- PEB = Prompt Engineering Bootcamp
- LCA = LangChain Academy
- DLAI = DeepLearning.AI
- Ng = DLAI Agentic AI
- HF = Hugging Face
- HS = Hamel & Shreya
- ANT = Anthropic Academy
- SK = Steve Kinney
- LC = Laracasts
- HBA = Hugo Bowne-Anderson
- FSDL = Full Stack Deep Learning
- BRK = Berkeley MOOC
- EAC = Elite AI-Assisted Coding

| Topic | Courses that teach it | Status vs draft |
|---|---|---|
| What is an agent; degrees of autonomy | Ng, HF, UD, ED-A, BRK | covered (M00/M06) |
| LLM fundamentals: tokens, messages, special tokens, chat templates | HF, PEB, ANT, FSDL | covered (M01) |
| Sampling and temperature | ANT, PEB | covered (M01) |
| Reasoning models and extended thinking | ANT | covered (M01) |
| Multi-provider and open-source models (Ollama, HF, OpenAI-compatible endpoints) | ED-C, ED-A, HF | partial (M01). Add a short "provider-agnostic harness" note |
| Fine-tuning (LoRA/QLoRA, function-calling FT, distillation, SFT/RL) | ED-C, HF bonus 1, HS L9 (as a last resort) | out-of-scope. Mention only as HS's "weights track: use when prompt search is flat" in M09 |
| Prompting techniques (role, CoT, ReAct, XML, examples, five principles) | UD, PEB, EM, ANT, FSDL | covered (M02) |
| Prompt instruction refinement and the prompt lifecycle; prompt hub and versioning | UD, LCA (Prompt Hub, Lifecycle) | covered (M02) |
| Prompt chaining | UD, ANT | covered (M06) |
| Structured outputs (Pydantic, schemas) | UD, LCA, ED-A, ANT | covered (M11) |
| Context engineering: trim, filter, summarize, offload | LCA (LangGraph M2, Deep Agents M3, LangChain M3), ED-A W6, EM, EAC | covered (M03) |
| Memory taxonomy: short vs long-term; semantic, episodic, procedural; memory stores | LCA (LangGraph M5), DLAI LT-Memory, UD C3, LCA Deployment M4 | partial (M03). Add the taxonomy |
| RAG and agentic RAG (chunking, embeddings, BM25, vector DBs, multi-index) | UD, ED-C W5, EM, PEB, HF U3, ANT, ED-A W6 | partial (M03 says "retrieval"). Every course has it, so give it an explicit lesson |
| RAG evaluation (retrieval and grounding evals) | HS L5, ED-C W5 [inferred] | MISSING. Add to M07/M08 |
| Agentic coding: explore → plan → code → verify, worktrees, GitHub, hooks | DLAI Claude Code, ANT Claude Code in Action, SK, LC, EAC | covered (M04) |
| Spec-driven development (constitution, spec, validate, replan, legacy) | DLAI SDD, HS L1 (SPEC.md with risk tiers), EAC, LC (PRDs) | partial (M02/M14). Make it an explicit workflow in M04 |
| Tool definition and tool schemas; function calling | UD, Ng M3, HF, ANT, EM, ED-A | covered (M05) |
| MCP: servers, clients, resources, prompts, remote, inspector, sampling | DLAI MCP, ANT (2 courses), LCA, ED-A W6, Ng | covered (M05) |
| Agent Skills (vs tools, MCP, subagents) | DLAI Skills, ANT, LCA Deep Agents, SK, ED-A W4 | covered (M05) |
| Hooks and permission modes | DLAI Claude Code, ANT, SK, LC | covered (M05/M11) |
| Code execution as a tool; code-as-action (CodeAgent) vs JSON tool calls | HF U2.1, Ng M3/M5 ("planning with code execution"), ANT | MISSING. Add to M05/M06 |
| Execution environments and sandboxes (filesystem backends, local shell, computer use) | LCA Deep Agents M2, LCA Fleet, ED-A W2 D3, LC, EAC | partial (M10 sandboxed environments). Give it a harness lesson in M05/M13 |
| Workflow patterns: chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer | UD C2, ANT, Ng, LCA LangGraph M4 (map-reduce, sub-graphs) | covered (M06) |
| Reflection pattern (with external feedback) | Ng M2, EM [unverified], ED-A Sidekick | covered (M06/M06b) |
| Planning pattern (plan-then-execute; plans as code) | Ng M5, Deep Agents, LCA Deep Research (scoping) | partial (M06). Name it explicitly |
| Multi-agent systems: architecture, supervisor, shared state, communication | UD C4, Ng M5, DLAI crewAI, LCA Deep Research, HF, ED-A, BRK | covered (M06) |
| Subagents and delegation, dynamic and asynchronous subagents | LCA Deep Agents M4/M5, ANT Subagents, SK | covered (M04/M06) |
| Agent-to-agent protocol (A2A) | ED-A W5 (Google ADK + A2A) | MISSING. A brief mention in M05/M06 is enough |
| Orchestration by code vs by LLM | ED-A W2 D2, ANT (workflows vs agents) | covered (M06) |
| Agent loop internals: TAO cycle, ReAct parsing, dummy agent library | HF U1, EM, ED-A W2, DLAI LangGraph, HBA | covered (M06b) |
| Generate → verify → fix self-correction loops | UD C1, Ng M2, ED-A, SK | covered (M06b) |
| Long-running autonomous loops: Ralph, headless, routines and schedules | SK, LC, ANT Claude Code in Action, LCA Deep Agents | covered (M06b) |
| Loop oracle design, governor, stall detection, typed exit codes, disposable checkouts | SK (in depth), ED-A (time limits, one fix) | covered (M06b). Adopt SK's structure |
| Running loops in the background or remotely (tmux, SSH, remote workers) | LC, SK | partial (M06b). Add an ops lab |
| Ambient or event-driven agents (triggered by email, events, cron) | LCA Ambient, LCA Fleet, DLAI Event-Driven | MISSING. Add to M06b |
| Frameworks: LangGraph state, reducers, nodes, edges, conditional edges | LCA, DLAI LangGraph, HF U2.3, EM, ED-A W4 | covered (M06c) |
| Checkpointers, threads, persistence; time travel (fork or replay a run) | LCA LangGraph M3, Deep Agents M1, DLAI LangGraph | covered (M06c). Reuse time travel in M10 record/replay |
| Human-in-the-loop interrupts, breakpoints, state editing | LCA (nearly every course), DLAI LangGraph, ED-A Sidekick, LC | covered (M06c/M11) |
| Middleware (LangChain v1), dynamic prompts, dynamic agents | LCA LangChain M3, Essentials, ED-A W4 | covered (M06c) |
| Deep agents harness | LCA Deep Agents, dcode, ED-A W4 | covered (M06c) |
| Other frameworks: OpenAI Agents SDK, CrewAI, Google ADK, Pydantic AI, Strands, LlamaIndex, smolagents, Mastra | ED-A (all of them), HF (smolagents, LlamaIndex), DLAI crewAI, HS (OpenAI SDK) | partial (M06c is LangChain-only). Add a framework-selection comparison |
| Streaming and agent UIs (Agent Chat UI, Gradio, generative UI) | LCA, ED-C, ED-A | out-of-scope (front-end). Mention briefly |
| UX for agentic systems (trust, review, interrupt affordances) | FSDL | MISSING. Short section in M11/M14 |
| Deployment: agent servers, assistants, custom routes, managed deep agents | LCA LangGraph M6, LCA Deployment | partial (M12). Mostly vendor-specific |
| Concurrency: double texting (reject, enqueue, interrupt, rollback) | LCA LangGraph M6 | MISSING. Ideal for a distributed-systems learner (M06c/M12) |
| Multi-tenant auth and authorization for agents | LCA Deployment M5, HS L7 (permissions in code; authz holds when the model is compromised) | partial (M13). Make authorization-as-the-real-boundary explicit |
| Evals: datasets, experiments, code-based, LLM-judge, human grading | LCA (several), DLAI Eval Agents, ANT, Ng M4, HS, UD | covered (M07/M08) |
| Error analysis: open and axial coding, failure taxonomy, saturation | HS L4, Ng M4 | covered (M07) |
| Binary per-failure-mode evaluators; judge train/dev/test; TPR/TNR | HS L5 | covered (M08) |
| Pairwise evals and summary (aggregate) evaluators | LCA (Intro to LangSmith, Reliable Agents) | MISSING. Add to M08 |
| Synthetic data and scenario generation; deterministic simulated world (facts.yaml) | HS L3, ANT (generating test datasets) | partial (M10 simulated users). Make it an explicit lesson in M07/M10 |
| Eval statistics: bootstrap CIs, prevalence correction, eval noise | HS L5/L6, BRK (Predictable Noise) | covered (M09) |
| pass@k vs pass^k; reset-and-replay failure rate | HS L6 | covered (M07/M10) |
| Component-level vs end-to-end evals (router vs skill) | Ng M4, DLAI Eval Agents | partial (M10). Name it |
| Trajectory evals; convergence or step-efficiency score | DLAI Eval Agents, UD C3, Ng | covered (M10) |
| CI/CD eval gates; tiered cost (deterministic, mocked, full) | HS L6, DLAI LLMOps, FSDL LLMOps, EAC | partial (M09 regression suites). Add a CI gate lab |
| Public benchmarks as a target (GAIA leaderboard) | HF U4, BRK (AgentBeats) | MISSING. Use in M09 or the capstone |
| Instrumentation and trace data model before launch (spans, prompt hashes) | HS L2, LCA (tracing), DLAI Eval Agents, ED-A, HF bonus 2 | partial (M12 is too late). Move tracing earlier (M06/M07) |
| Hill-climbing loop, manual first; fix-routing to the cheapest layer | HS L8, Ng M4 | covered (M09) |
| Automated prompt or harness optimization (GEPA, DSPy, bounded improve-loop, LangSmith Engine, Polly) | HS L8, LCA Engine, LCA (Polly), PEB "Prompt Optimization & Evals" | MISSING. Add to M09 |
| Accuracy-vs-cost frontier; model-upgrade drill | HS L8/L9 | partial (M09/M12). Make it an explicit lab |
| Production monitoring: online evals, automations, dashboards, insights | LCA (several), HS L6, DLAI Eval Agents | covered (M12) |
| Human feedback collection: user feedback, annotation queues | LCA | partial (M08/M12) |
| Monitoring user sentiment and A/B tests | LCA Monitoring M3 | MISSING. Add to M12 |
| Cost: token breakdowns, prompt caching, routing, cascades | LCA Monitoring M1, HS L9, ANT, SK (Cache Money), Ng M4 | covered (M12) |
| Guardrails: input, output, tool; PII; on-topic; NLI hallucination checks | DLAI Guardrails, ED-A W2, HS L7 | covered (M11/M13) |
| Red-teaming (promptfoo); attacks become regression tests | HS L7 | partial (M13). Add a lab |
| OWASP Top 10 for Agentic Apps; the lethal trifecta; security monitoring and alerts | HS L7, LCA Monitoring M4, BRK (Dawn Song) | covered (M13) |
| Governance: NIST AI RMF, EU AI Act, risk tiers | HS L1/L7 | MISSING. A short M13/M14 note |
| Reward hacking in improvement loops; agents mustn't grade their own work | HS L8, HBA, SK | covered (M13/M06b). Cross-link |
| The ADLC (build → test → deploy → monitor → improve) | LCA, LCAE | partial. Use it as the spine for M07–M12 |
| Recovering a failing or drifting session; steering long sessions | SK, ANT | covered (M11) |
| AI fluency, capabilities and limitations | ANT | covered (M00/M01) |
| Domain projects: knowledge graphs, on-device memory, games (Pokémon), image and video models | DLAI, HF bonus 3, PEB | out-of-scope (not core to engineering rigor) |
| No-code agent builders (LangSmith Fleet, n8n) | LCA Fleet, Udemy n8n | out-of-scope (the audience is experienced engineers) |
| Evals interview prep | HS bonus | out-of-scope |

---

## 10. Recommended additions to the draft

Ordered by value to the course's audience. Each item names the module it belongs in.

1. **Design for evaluability early (tracing in M06/M07, not only M12).** Hamel L2 builds the trace data model (nested spans, tool calls, permission denials, prompt hashes) *before* users arrive. LangChain's ADLC and DL.AI's Evaluating Agents both make tracing step 1. **Why:** error analysis in M07 is impossible without traces. Teaching observability last inverts the dependency.

2. **Synthetic scenario generation and deterministic simulated worlds (M07/M10).** Hamel L3 (`facts.yaml`, about 500 generated scenarios, smoke report) and Anthropic's "generating test datasets". **Why:** the draft has "golden datasets" and "simulated users" but not how to bootstrap a dataset before production traffic exists. That is the real cold-start problem.

3. **Automated optimization of prompts and harnesses (M09).** GEPA/DSPy, Hamel's "bounded improve-loop", LangSmith Engine, and LangSmith Polly. **Why:** this is the logical end of hill-climbing and is where loops (06b) meet evals (09). Teach it *after* a manual loop, with reward-hacking guards, as Hamel does.

4. **Accuracy-vs-cost frontier, fix routing, and the model-upgrade drill (M09/M12).** Hamel L8/L9: vary one axis at a time; fix at the cheapest layer (prompt → tools → harness → model); keep variants as configs and re-run the suite when a model ships. **Why:** this is the engineering-management skill a senior engineer will be asked for ("should we move to the new model?").

5. **Ambient, event-driven, and headless/CI agents (M06b).** LangChain Ambient Agents, LangSmith Fleet, Anthropic "Routines and Headless", and Laracasts background and remote loops. **Why:** 06b covers loops but not agents triggered by events (email, webhooks, cron) or running in CI. That is where autonomous agents live in production.

6. **Execution environments and sandboxes as a first-class harness concern (M05/M13).** Deep Agents M2 (filesystem backends, sandboxes, interpreter), plus code-as-action vs JSON tool calls (HF smolagents, Ng "planning with code execution"). **Why:** the sandbox is both the capability boundary and the security boundary, and it is what makes long loops safe.

7. **Concurrency and durability of stateful agents (M06c/M12).** LangGraph checkpointers, time travel, and **double texting** (reject, enqueue, interrupt, rollback), plus threads and assistants. **Why:** this is where distributed-systems experience transfers directly. Frame it with idempotency, event sourcing, and optimistic concurrency, and reuse time travel for record/replay in M10.

8. **Framework selection beyond LangChain (M06c).** Ed Donner builds the same worker in OpenAI Agents SDK, CrewAI, Google ADK (+A2A), Pydantic AI, Strands, MS Agent Framework, Agno, and Mastra. **Why:** "when does a framework help?" needs at least one non-LangChain comparator, and the OpenAI Agents SDK is what Hamel's evals course uses. Give A2A one paragraph.

9. **An explicit RAG and memory lesson (M03).** Agentic RAG appears in nearly every course (Udacity, Ed Donner, Eden Marco, HF, Anthropic). Add the semantic, episodic, and procedural memory taxonomy (DL.AI LT-Memory) and RAG and grounding evals (Hamel L5). **Why:** "retrieval" is currently one word in M03, while it is the most-taught topic in the union.

10. **Eval primitives we lack (M08/M12).** Pairwise evaluators, summary or aggregate evaluators, annotation queues, user-sentiment monitoring, and A/B tests (LangChain Academy). **Why:** these are cheap to teach and fill out the evaluator toolbox.

11. **A CI eval-gate lab and red-team-to-regression lab (M09/M13).** Hamel L6 (tiered deterministic, mocked, and full evals; GitHub Actions gate) and L7 (promptfoo attacks become failing tests). DL.AI LLMOps is a lighter version. **Why:** this turns the eval suite into infrastructure, which is the staff-level deliverable.

12. **Spec-driven development as a concrete workflow (M04/M14).** The DL.AI SDD course (constitution → spec → implement → validate → replan; legacy codebases; agent replaceability) and Hamel's SPEC.md with risk tiers. **Why:** "specs as source" in M14 needs a hands-on loop, and the SPEC.md doubles as the eval contract in M07.

13. **Adopt Kinney's control-loop anatomy for M06b.** Use measure → pick → run → accept → governor, the oracle-quality ranking, "write the oracle first and prove it can fail", typed exit codes, and disposable checkouts. **Why:** it is the most rigorous loop material found, and it maps directly onto the planned Kubernetes reconciler analogy.

14. **Public benchmark as an external grader (M09/M99).** HF's GAIA leaderboard and Berkeley's AgentBeats. **Why:** a held-out grader the student can't edit is the cleanest demonstration of "don't let agents grade their own work", and it is a credible capstone metric.

15. **Small additions:**
    - Governance (NIST AI RMF, EU AI Act, risk tiers) in M13/M14.
    - Agent UX (FSDL "UX for LUIs") in M11.
    - Measuring whether reflection actually helps (Ng M2) as a mini-lab in 06b.
