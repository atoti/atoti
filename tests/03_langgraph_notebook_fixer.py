#!/usr/bin/env python3
"""
LangGraph-based Jupyter Notebook Fixing and API Upgrade System

This system uses LangGraph to create a sophisticated workflow that follows the exact 5-step process:

🔄 **5-STEP ITERATIVE WORKFLOW:**
1. **Test Notebook** → Execute notebook to analyze any errors (execute_notebook node)
2. **Analyze Error** → Extract error details and build targeted RAG queries (analyze_execution_errors node)
3. **RAG Search** → Search documentation for solutions using error-specific queries (search_rag_solutions node)
4. **Plan & Apply Fix** → Determine new working code and update broken cells (plan_code_upgrade + apply_code_changes nodes)
5. **Validate & Iterate** → Retest notebook and repeat until all errors resolved (validate_notebook_fix node)

🚀 **Key Features:**
- Uses RAG from your vectordb for intelligent error resolution
- Detects API version compatibility issues with targeted searches
- Plans and executes upgrades using Ollama's Devstral model
- Handles complex conditional logic and error recovery with circuit breakers
- Provides comprehensive state management across the entire upgrade process
- Complete transparency with untruncated logging for full visibility
"""

import json
import subprocess
import logging
import time
from typing import Dict, Any, List, Optional, TypedDict
from datetime import datetime
import re

# LangGraph imports
from langgraph.graph import StateGraph, END

# LangChain imports for tools and LLMs
from langchain_core.tools import BaseTool
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_chroma import Chroma

# Configuration constants
NOTEBOOK_EXECUTION_TIMEOUT = 120  # seconds
MAX_FILE_CONTENT_PREVIEW = None  # No character limit - show everything


def setup_logging(log_level=logging.INFO):
    """Set up comprehensive logging for the notebook upgrade process."""
    # Create formatter with timestamp and emojis for better readability
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S"
    )

    # Console handler with color-coded levels
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # File handler for persistent logs
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"notebook_upgrade_{timestamp}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)

    # Configure root logger
    logger = logging.getLogger("notebook_upgrader")
    logger.setLevel(log_level)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    logger.info(f"📋 Logging initialized - Console + File ({log_file})")
    return logger


def log_state_transition(logger, from_node: str, to_node: str, state: Dict[str, Any]):
    """Log detailed state transitions between workflow nodes."""
    logger.info(f"🔄 TRANSITION: {from_node} → {to_node}")
    logger.info(f"   📊 Status: {state.get('upgrade_status', 'unknown')}")
    logger.info(
        f"   🔢 Iteration: {state.get('iteration_count', 0)}/{state.get('max_iterations', 0)}"
    )

    # Log error details if present
    if state.get("execution_error"):
        logger.warning(f"   ⚠️  Error: {state['execution_error']}")

    # Log progress indicators
    if state.get("breaking_changes"):
        logger.info(f"   🔧 Breaking changes found: {len(state['breaking_changes'])}")

    if state.get("rag_search_results"):
        logger.info(f"   📚 RAG results: {len(state['rag_search_results'])} documents")


def log_tool_execution(
    logger, tool_name: str, params: Dict[str, Any], result: str, duration: float
):
    """Log detailed tool execution information."""
    logger.info(f"🔧 TOOL: {tool_name} (⏱️ {duration:.2f}s)")

    # Log key parameters (full content)
    for key, value in params.items():
        logger.debug(f"   📝 {key}: {value}")

    # Log full result
    if "❌" in result:
        logger.warning(f"   ❌ Result: {result}")
    elif "✅" in result:
        logger.info(f"   ✅ Result: {result}")
    else:
        logger.debug(f"   📄 Result: {result}")


def log_workflow_progress(logger, state: Dict[str, Any]):
    """Log detailed workflow progress and metrics with complete state visibility."""
    progress_percent = (
        state.get("iteration_count", 0) / max(state.get("max_iterations", 1), 1)
    ) * 100

    logger.info("=" * 80)
    logger.info(f"📈 WORKFLOW PROGRESS: {progress_percent:.1f}%")
    logger.info("=" * 80)
    logger.info(f"📁 Notebook: {state.get('notebook_path', 'Unknown')}")
    logger.info(f"🎯 Target API: {state.get('target_api_version', 'Latest')}")
    logger.info(f"📊 Status: {state.get('upgrade_status', 'Unknown')}")
    logger.info(
        f"🔄 Iteration: {state.get('iteration_count', 0)}/{state.get('max_iterations', 0)}"
    )
    logger.info(
        f"🚨 Search Attempts: {state.get('search_attempts', 0)}/{state.get('max_search_attempts', 3)}"
    )
    logger.info(
        f"🧠 Planning Attempts: {state.get('planning_attempts', 0)}/{state.get('max_planning_attempts', 3)}"
    )

    # Show complete state details
    if state.get("execution_error"):
        logger.info("📋 CURRENT EXECUTION ERROR:")
        logger.info(f"   {state['execution_error']}")

    if state.get("error_details"):
        error_details = state["error_details"]
        logger.info("🔍 EXTRACTED ERROR DETAILS:")
        logger.info(f"   🐛 Type: {error_details.get('error_type', 'Unknown')}")
        logger.info(f"   💬 Message: {error_details.get('error_message', 'Unknown')}")
        logger.info(
            f"   � Failing Code: {error_details.get('failing_code', 'Not detected')}"
        )

    if state.get("rag_search_results"):
        logger.info(
            f"📚 RAG SEARCH RESULTS: {len(state['rag_search_results'])} searches completed"
        )
        for i, result in enumerate(state["rag_search_results"], 1):
            result_preview = result[:200] if len(result) > 200 else result
            logger.info(f"   📄 Search {i}: {result_preview}...")

    if state.get("migration_plan"):
        plan = state["migration_plan"]
        logger.info("📋 MIGRATION PLAN:")
        logger.info(f"   📊 Status: {plan.get('status', 'Unknown')}")
        if plan.get("before_code"):
            logger.info(f"   � Before Code: {len(plan['before_code'])} characters")
        if plan.get("after_code"):
            logger.info(f"   ✨ After Code: {len(plan['after_code'])} characters")
        if plan.get("reasoning"):
            logger.info(f"   🧠 Reasoning: {plan['reasoning']}")

    if state.get("backup_paths"):
        logger.info(f"📁 BACKUPS: {len(state['backup_paths'])} files created")
        for backup in state["backup_paths"]:
            logger.info(f"   💾 {backup}")

    logger.info("=" * 80)


class NotebookUpgradeState(TypedDict):
    """State object that tracks the entire notebook upgrade process"""

    notebook_path: str
    current_api_version: Optional[str]
    target_api_version: str
    execution_error: Optional[str]
    breaking_changes: List[Dict[str, Any]]
    migration_plan: Dict[str, Any]
    before_code: Optional[str]
    after_code: Optional[str]
    upgrade_status: (
        str  # "pending", "analyzing", "planning", "applying", "success", "failed"
    )
    error_details: Dict[str, Any]
    rag_search_results: List[str]
    iteration_count: int
    max_iterations: int
    backup_paths: List[str]
    final_result: Dict[str, Any]
    # Circuit breaker fields
    search_attempts: int
    planning_attempts: int
    max_search_attempts: int
    max_planning_attempts: int


class NotebookExecutionTool(BaseTool):
    """Tool for executing notebook cells and capturing output."""

    name: str = "notebook_execution"
    description: str = (
        "Execute a Jupyter notebook and return the output or error. "
        "Use notebook_path parameter with the complete file path to the .ipynb file."
    )

    def _run(self, notebook_path: str) -> str:
        """Execute a Jupyter notebook and return the output or error."""
        try:
            import nbformat
            from nbconvert.preprocessors import ExecutePreprocessor
            import os

            # Read the notebook
            with open(notebook_path, "r", encoding="utf-8") as f:
                notebook = nbformat.read(f, as_version=4)

            # Execute the notebook
            ep = ExecutePreprocessor(
                timeout=NOTEBOOK_EXECUTION_TIMEOUT, kernel_name="python3"
            )
            ep.preprocess(
                notebook, {"metadata": {"path": os.path.dirname(notebook_path)}}
            )

            return "✅ SUCCESS: Notebook executed without errors"

        except Exception as e:
            error_msg = str(e)
            if hasattr(e, "output") and e.output:
                error_msg = e.output
            elif hasattr(e, "traceback") and e.traceback:
                error_msg = e.traceback
            return f"❌ EXECUTION ERROR: {error_msg}"


class RAGSearchTool(BaseTool):
    """Tool for searching the atoti documentation vectordb."""

    name: str = "rag_search"
    description: str = (
        "Search the atoti documentation using RAG to find relevant information. "
        "Use 'query' parameter for the search text."
    )

    def __init__(
        self,
        vectordb_path: str = "/Users/aya/Desktop/atoti/atoti_docs_vectordb",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._vectordb_path = vectordb_path
        self._vectordb = None
        self._embeddings = None
        self._initialize_rag()

    def _initialize_rag(self):
        """Initialize the RAG system with existing vectordb."""
        try:
            self._embeddings = OllamaEmbeddings(model="mxbai-embed-large")
            self._vectordb = Chroma(
                persist_directory=self._vectordb_path,
                embedding_function=self._embeddings,
            )
            # Test the connection with a simple query
            test_docs = self._vectordb.similarity_search("atoti", k=1)
            doc_count = len(test_docs) if test_docs else 0
            print(
                f"✅ RAG system initialized - Connected to vectordb with {doc_count} test documents"
            )
            print(f"📚 Vectordb location: {self._vectordb_path}")
        except Exception as e:
            print(f"❌ Failed to initialize RAG system: {e}")
            print(f"🔍 Check if vectordb exists at: {self._vectordb_path}")

    def _run(self, query: str) -> str:
        """Search the vectordb for relevant documentation."""
        if not self._vectordb:
            return "❌ RAG system not initialized - cannot perform search"

        try:
            start_time = time.time()
            docs = self._vectordb.similarity_search(query, k=5)
            search_time = time.time() - start_time

            if not docs:
                return f"❌ No relevant documentation found for query: '{query}'"

            context = "\n\n".join(
                [f"Document {i + 1}:\n{doc.page_content}" for i, doc in enumerate(docs)]
            )

            # Add search metadata
            result = f"📚 Found {len(docs)} relevant documents (⏱️ {search_time:.2f}s):\n\n{context}"
            return result

        except Exception as e:
            return f"❌ RAG search failed for query '{query}': {e}"


class NotebookEditTool(BaseTool):
    """Tool for editing notebook cells based on before/after code snippets."""

    name: str = "notebook_edit"
    description: str = (
        "Edit notebook cells by replacing before_code with after_code. "
        "Requires notebook_path, before_code, and after_code parameters."
    )

    def _run(self, notebook_path: str, before_code: str, after_code: str) -> str:
        """Apply code changes to the notebook."""
        try:
            import nbformat

            # Read the notebook
            with open(notebook_path, "r", encoding="utf-8") as f:
                notebook = nbformat.read(f, as_version=4)

            # Find code cells only
            code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]

            if not code_cells:
                return "❌ No code cells found in the notebook."

            # Find matching cell
            target_cell_index = self._find_matching_cell(before_code, code_cells)
            if target_cell_index is None:
                return "❌ Could not find matching cell for the before_code."

            # Apply the fix
            return self._apply_fix(
                notebook, code_cells, target_cell_index, after_code, notebook_path
            )

        except Exception as e:
            return f"❌ Edit failed: {str(e)}"

    def _find_matching_cell(self, target_code: str, code_cells: list) -> int:
        """Find the cell that best matches the target code."""
        target_lines = set(
            line.strip() for line in target_code.split("\n") if line.strip()
        )

        best_match_score = 0
        best_match_index = None

        for i, cell in enumerate(code_cells):
            cell_source = cell["source"].strip()
            cell_lines = set(
                line.strip() for line in cell_source.split("\n") if line.strip()
            )

            # Calculate similarity by counting common lines
            common_lines = len(target_lines.intersection(cell_lines))
            match_ratio = common_lines / max(len(target_lines), 1)

            # Prefer exact substring matches
            if target_code in cell_source or cell_source in target_code:
                return i
            elif match_ratio > best_match_score and match_ratio > 0.5:
                best_match_score = match_ratio
                best_match_index = i

        return best_match_index

    def _apply_fix(
        self,
        notebook,
        code_cells: list,
        target_index: int,
        new_content: str,
        notebook_path: str,
    ) -> str:
        """Apply the fix to the target cell and save the notebook."""
        import nbformat

        try:
            # Get the target cell
            target_cell = code_cells[target_index]

            # Update the cell content
            target_cell.source = new_content

            # Clear any previous outputs and execution count
            target_cell.outputs = []
            target_cell.execution_count = None

            # Save the notebook
            with open(notebook_path, "w", encoding="utf-8") as f:
                nbformat.write(notebook, f)

            return f"✅ Successfully edited code cell #{target_index + 1}"

        except Exception as e:
            return f"❌ Failed to apply fix: {str(e)}"


class NotebookUpgradeWorkflow:
    """LangGraph-based notebook upgrade workflow with state management."""

    def __init__(
        self, vectordb_path: str = "/Users/aya/Desktop/atoti/atoti_docs_vectordb"
    ):
        self.vectordb_path = vectordb_path
        self.logger = setup_logging()
        self.workflow_start_time = None
        self.current_node = "initialization"

        self.logger.info("🚀 Initializing NotebookUpgradeWorkflow")
        self.llm = self._initialize_llm()
        self.tools = self._initialize_tools()
        self.workflow = self._create_workflow()
        self.logger.info("✅ NotebookUpgradeWorkflow fully initialized")

    def _initialize_llm(self):
        """Initialize Ollama Devstral model."""
        try:
            self.logger.info("🤖 Initializing Devstral LLM...")
            llm = ChatOllama(
                model="devstral:latest",
                temperature=0.0,  # Deterministic for structured output
                base_url="http://localhost:11434",
            )
            self.logger.info("✅ Devstral model initialized successfully")
            return llm
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Devstral model: {e}")
            return None

    def _initialize_tools(self):
        """Initialize all tools for the workflow."""
        self.logger.info("🔧 Initializing workflow tools...")
        tools = {
            "notebook_execution": NotebookExecutionTool(),
            "rag_search": RAGSearchTool(self.vectordb_path),
            "notebook_edit": NotebookEditTool(),
        }
        self.logger.info("✅ All tools initialized successfully")
        return tools

    def _create_workflow(self) -> StateGraph:
        """Create the LangGraph workflow with conditional routing."""
        workflow = StateGraph(NotebookUpgradeState)

        # Add nodes for each step in the process
        workflow.add_node("initialize", self.initialize_upgrade)
        workflow.add_node("execute_notebook", self.execute_notebook)
        workflow.add_node("analyze_errors", self.analyze_execution_errors)
        workflow.add_node(
            "try_direct_fix", self.try_direct_llm_fix
        )  # NEW: Try LLM first
        workflow.add_node("search_solutions", self.search_rag_solutions)
        workflow.add_node("plan_upgrade", self.plan_code_upgrade)
        workflow.add_node("apply_changes", self.apply_code_changes)
        workflow.add_node("validate_fix", self.validate_notebook_fix)
        workflow.add_node("finalize_results", self.finalize_upgrade_results)

        # Set entry point
        workflow.set_entry_point("initialize")

        # Add conditional edges for complex routing
        workflow.add_conditional_edges(
            "execute_notebook",
            self.route_after_execution,
            {
                "success": "finalize_results",
                "error": "analyze_errors",
                "max_iterations": "finalize_results",
            },
        )

        workflow.add_conditional_edges(
            "analyze_errors",
            self.route_after_error_analysis,  # NEW: Route to direct fix or RAG
            {
                "direct_fix": "try_direct_fix",
                "rag_search": "search_solutions",
            },
        )

        workflow.add_conditional_edges(
            "try_direct_fix",
            self.route_after_direct_fix,  # NEW: Route based on direct fix result
            {
                "apply": "apply_changes",
                "rag_fallback": "search_solutions",
                "no_solution": "finalize_results",
            },
        )

        workflow.add_conditional_edges(
            "search_solutions",
            self.route_after_search,
            {
                "plan": "plan_upgrade",
                "max_search": "finalize_results",
            },
        )

        workflow.add_conditional_edges(
            "plan_upgrade",
            self.route_after_planning,
            {
                "apply": "apply_changes",
                "needs_more_info": "search_solutions",
                "no_solution": "finalize_results",
            },
        )

        workflow.add_conditional_edges(
            "validate_fix",
            self.route_after_validation,
            {
                "success": "finalize_results",
                "retry": "analyze_errors",
                "max_iterations": "finalize_results",
            },
        )

        # Linear edges
        workflow.add_edge("initialize", "execute_notebook")
        workflow.add_edge("apply_changes", "validate_fix")
        workflow.add_edge("finalize_results", END)

        self.logger.info("✅ LangGraph workflow created successfully")
        compiled_workflow = workflow.compile()

        # Configure workflow with higher recursion limit
        try:
            compiled_workflow = workflow.compile(config={"recursion_limit": 50})
            self.logger.info("🔧 Workflow configured with recursion_limit=50")
        except Exception as e:
            self.logger.warning(f"⚠️ Could not set recursion limit: {e}")
            compiled_workflow = workflow.compile()

        return compiled_workflow

    def upgrade_notebook(
        self, notebook_path: str, max_iterations: int = 3
    ) -> Dict[str, Any]:
        """Main method to upgrade a notebook using the LangGraph workflow."""
        self.workflow_start_time = time.time()
        self.logger.info("=" * 60)
        self.logger.info("🎯 STARTING NOTEBOOK UPGRADE WORKFLOW")
        self.logger.info("=" * 60)
        self.logger.info(f"📁 Target notebook: {notebook_path}")
        self.logger.info(f"🔄 Max iterations: {max_iterations}")

        # Initial state
        initial_state: NotebookUpgradeState = {
            "notebook_path": notebook_path,
            "current_api_version": None,
            "target_api_version": "latest",
            "execution_error": None,
            "breaking_changes": [],
            "migration_plan": {},
            "before_code": None,
            "after_code": None,
            "upgrade_status": "pending",
            "error_details": {},
            "rag_search_results": [],
            "iteration_count": 0,
            "max_iterations": max_iterations,
            "backup_paths": [],
            "final_result": {},
            # Circuit breaker initialization
            "search_attempts": 0,
            "planning_attempts": 0,
            "max_search_attempts": 3,
            "max_planning_attempts": 3,
        }

        try:
            # Run the workflow with configuration
            self.logger.info(
                "🚀 Invoking LangGraph workflow with enhanced circuit breakers..."
            )
            final_state = self.workflow.invoke(
                initial_state, config={"recursion_limit": 50}
            )

            # Calculate total time
            total_time = time.time() - self.workflow_start_time
            self.logger.info(f"⏱️ Total workflow time: {total_time:.2f} seconds")

            # Log final results
            success = final_state.get("upgrade_status") == "success"
            self.logger.info("=" * 60)
            if success:
                self.logger.info("🎉 WORKFLOW COMPLETED SUCCESSFULLY!")
            else:
                self.logger.warning("😞 WORKFLOW COMPLETED WITH ISSUES")
            self.logger.info("=" * 60)

            return {
                "success": success,
                "notebook_path": notebook_path,
                "final_status": final_state.get("upgrade_status"),
                "iterations": final_state.get("iteration_count"),
                "total_time": total_time,
                "backup_paths": final_state.get("backup_paths", []),
                "error": final_state.get("execution_error") if not success else None,
            }

        except Exception as e:
            total_time = time.time() - self.workflow_start_time
            self.logger.error(f"💥 WORKFLOW FAILED: {str(e)}")
            self.logger.error(f"⏱️ Failed after: {total_time:.2f} seconds")
            return {
                "success": False,
                "notebook_path": notebook_path,
                "error": str(e),
                "total_time": total_time,
                "timestamp": datetime.now().isoformat(),
            }

    # Node Functions (State Processors)

    def initialize_upgrade(self, state: NotebookUpgradeState) -> NotebookUpgradeState:
        """Initialize the upgrade process and create backup."""
        node_start_time = time.time()
        self.current_node = "initialize"
        self.logger.info("🚀 NODE: initialize_upgrade")
        self.logger.info(f"📁 Target notebook: {state['notebook_path']}")

        try:
            # Create backup
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{state['notebook_path']}.backup.{timestamp}.{state['iteration_count']}"
            subprocess.run(["cp", state["notebook_path"], backup_path], check=True)

            state["backup_paths"].append(backup_path)
            state["upgrade_status"] = "analyzing"

            node_time = time.time() - node_start_time
            self.logger.info(f"📁 Created backup: {backup_path}")
            self.logger.info(f"✅ initialize_upgrade completed in {node_time:.2f}s")

            log_workflow_progress(self.logger, state)
            return state

        except Exception as e:
            self.logger.error(f"❌ initialize_upgrade failed: {e}")
            state["upgrade_status"] = "failed"
            state["execution_error"] = f"Backup creation failed: {e}"
            return state

    def execute_notebook(self, state: NotebookUpgradeState) -> NotebookUpgradeState:
        """STEP 1: Execute the notebook and capture any errors."""
        node_start_time = time.time()
        self.current_node = "execute_notebook"

        log_state_transition(self.logger, "initialize", "execute_notebook", state)
        self.logger.info("🔄 STEP 1: TESTING NOTEBOOK TO ANALYZE ERRORS")
        self.logger.info(
            f"📱 Executing notebook (iteration {state['iteration_count']})"
        )

        execution_result = self.tools["notebook_execution"]._run(state["notebook_path"])
        execution_time = time.time() - node_start_time

        log_tool_execution(
            self.logger,
            "notebook_execution",
            {"notebook_path": state["notebook_path"]},
            execution_result,
            execution_time,
        )

        state["execution_error"] = execution_result

        if "✅ SUCCESS" in execution_result:
            self.logger.info(
                "✅ STEP 1 COMPLETE: Notebook executed successfully - no errors to fix!"
            )
            state["upgrade_status"] = "success"
        else:
            self.logger.info(
                "❌ STEP 1 COMPLETE: Found errors - proceeding to analysis"
            )
            state["upgrade_status"] = "error"

        self.logger.info(f"⏱️ Step 1 completed in {execution_time:.2f}s")
        log_workflow_progress(self.logger, state)
        return state

    def analyze_execution_errors(
        self, state: NotebookUpgradeState
    ) -> NotebookUpgradeState:
        """STEP 2: Analyze execution errors to extract key information for RAG queries."""
        node_start_time = time.time()
        self.current_node = "analyze_errors"

        log_state_transition(self.logger, "execute_notebook", "analyze_errors", state)
        self.logger.info("🔍 STEP 2: ANALYZING ERRORS TO BUILD RAG QUERIES")
        self.logger.info(
            "📋 Extracting error details for targeted documentation search..."
        )

        error_msg = state["execution_error"]
        self.logger.info("📝 COMPLETE RAW ERROR MESSAGE:")
        self.logger.info("─" * 80)
        self.logger.info(error_msg)
        self.logger.info("─" * 80)

        # Extract error details using regex patterns
        error_details = {
            "error_type": self._extract_error_type(error_msg),
            "error_message": self._extract_error_message(error_msg),
            "failing_code": self._extract_failing_code(error_msg),
        }

        # Show detailed extraction process
        self.logger.info("🔧 ERROR EXTRACTION PROCESS:")
        self.logger.info(f"   🔍 Searching for error patterns in message...")
        self.logger.info(f"   ✅ Error Type: '{error_details['error_type']}'")
        self.logger.info(f"   ✅ Error Message: '{error_details['error_message']}'")
        self.logger.info(f"   ✅ Failing Code: '{error_details['failing_code']}'")

        state["error_details"] = error_details

        # Show what will be used for RAG queries
        self.logger.info("🎯 PREPARING RAG SEARCH STRATEGY:")
        if error_details.get("error_type"):
            self.logger.info(f"   � Will search: 'atoti {error_details['error_type']}'")
        if error_details.get("error_message"):
            self.logger.info(
                f"   📝 Will search: '{error_details['error_message']} atoti fix'"
            )
        self.logger.info("   � Will search: 'atoti Session.start SessionConfig'")
        self.logger.info("   📝 Will search: 'atoti API migration guide'")
        self.logger.info("   📝 Will search: 'atoti breaking changes latest version'")

        analysis_time = time.time() - node_start_time
        self.logger.info("✅ STEP 2 COMPLETE: Error analysis ready for RAG search")
        self.logger.info(f"⏱️ Step 2 completed in {analysis_time:.2f}s")

        log_workflow_progress(self.logger, state)
        return state

    def search_rag_solutions(self, state: NotebookUpgradeState) -> NotebookUpgradeState:
        """STEP 3: Search RAG for solutions using error-specific queries."""
        node_start_time = time.time()
        self.current_node = "search_solutions"

        log_state_transition(self.logger, "analyze_errors", "search_solutions", state)

        # Increment search attempts for circuit breaker
        state["search_attempts"] += 1
        self.logger.info("� STEP 3: SEARCHING DOCUMENTATION FOR SOLUTIONS")
        self.logger.info(
            f"🔍 RAG search attempt {state['search_attempts']}/{state['max_search_attempts']} using error analysis..."
        )

        # Circuit breaker check
        if state["search_attempts"] > state["max_search_attempts"]:
            self.logger.error(
                f"🚨 Circuit breaker triggered: Too many search attempts ({state['search_attempts']})"
            )
            state["upgrade_status"] = "failed"
            state["execution_error"] = (
                f"Maximum search attempts ({state['max_search_attempts']}) exceeded"
            )
            return state

        error_details = state["error_details"]
        error_msg = state["execution_error"]

        # Construct targeted search queries for minimal fixes
        queries = []

        # Add specific queries for this type of error
        if "create_session" in error_msg:
            queries.extend(
                [
                    "Session.start() simple example",
                    "tt.Session.start basic usage",
                    "create_session replaced Session.start",
                ]
            )
        elif "Session(" in error_msg:
            queries.extend(
                [
                    "Session() replaced Session.start",
                    "Session constructor deprecated",
                ]
            )

        # Add generic minimal upgrade queries
        queries.extend(
            [
                "atoti simple session creation",
                "basic session start example",
                "minimal atoti session setup",
            ]
        )

        self.logger.info(
            f"🎯 Built {len(queries)} targeted search queries from error analysis"
        )
        self.logger.debug(f"📝 Search queries: {queries}")

        # Perform RAG searches with complete visibility
        rag_results = []
        for i, query in enumerate(queries[:3]):  # Limit to 3 searches
            search_start_time = time.time()
            self.logger.info("─" * 80)
            self.logger.info(f"🔍 EXECUTING RAG SEARCH {i + 1}/3")
            self.logger.info(f"📝 Query: '{query}'")
            self.logger.info("🔄 Searching vectordb...")

            result = self.tools["rag_search"]._run(query)
            search_time = time.time() - search_start_time

            self.logger.info(f"⏱️ Search completed in {search_time:.2f}s")
            self.logger.info("📄 COMPLETE SEARCH RESULT:")
            self.logger.info(result)
            self.logger.info("─" * 80)

            log_tool_execution(
                self.logger, "rag_search", {"query": query}, result, search_time
            )
            rag_results.append(result)

        state["rag_search_results"] = rag_results

        total_search_time = time.time() - node_start_time
        self.logger.info(f"📚 Completed {len(queries[:3])} RAG searches")
        self.logger.info(
            "✅ STEP 3 COMPLETE: Documentation searched, ready for solution planning"
        )
        self.logger.info(f"⏱️ Step 3 completed in {total_search_time:.2f}s")

        log_workflow_progress(self.logger, state)
        return state

    def plan_code_upgrade(self, state: NotebookUpgradeState) -> NotebookUpgradeState:
        """STEP 4A: Analyze RAG results and plan the new working code."""
        node_start_time = time.time()
        self.current_node = "plan_upgrade"

        log_state_transition(self.logger, "search_solutions", "plan_upgrade", state)

        # Increment planning attempts for circuit breaker
        state["planning_attempts"] += 1
        self.logger.info("🧠 STEP 4A: DETERMINING NEW WORKING CODE FROM DOCUMENTATION")
        self.logger.info(
            f"📋 Planning upgrade strategy (attempt {state['planning_attempts']}/{state['max_planning_attempts']})..."
        )

        # Circuit breaker check
        if state["planning_attempts"] > state["max_planning_attempts"]:
            self.logger.error(
                f"🚨 Circuit breaker triggered: Too many planning attempts ({state['planning_attempts']})"
            )
            state["upgrade_status"] = "failed"
            state["migration_plan"] = {
                "status": "NO_SOLUTION",
                "reason": "Maximum planning attempts exceeded",
            }
            return state

        # Use LLM to analyze RAG results and create upgrade plan
        rag_context = "\n\n".join(state["rag_search_results"])
        error_context = str(state["error_details"])
        failing_code = state["error_details"].get(
            "failing_code", "No failing code extracted"
        )

        self.logger.info(
            "🤖 Analyzing documentation to determine correct code changes..."
        )
        self.logger.debug(f"📝 RAG context length: {len(rag_context)} characters")
        self.logger.debug(f"📝 Error context: {error_context}")

        error_details = state["error_details"]
        failing_code = error_details.get("failing_code", "No failing code extracted")
        error_msg = error_details.get("error_message", "Unknown error")

        prompt = f"""
        You are an expert at upgrading Jupyter notebooks to use the latest atoti API.
        
        TASK: Fix the EXACT failing code with the MINIMAL change needed.
        
        FAILING CODE:
        ```python
        {failing_code}
        ```
        
        ERROR: {error_msg}
        
        DOCUMENTATION SNIPPETS:
        {rag_context}
        
        INSTRUCTIONS:
        1. Make the SMALLEST possible change to fix the error
        2. Keep the same variable names and structure
        3. Only change what's broken - don't add extra complexity
        4. For session creation errors, typically just replace the method name
        
        Provide your response in this EXACT format:
        
        UPGRADE_STATUS: [READY | NEEDS_MORE_INFO | NO_SOLUTION]
        
        IF UPGRADE_STATUS: READY
        BEFORE_CODE:
        ```python
        # ==BEFORE==
        {failing_code}
        ```
        AFTER_CODE:
        ```python
        # ==AFTER==
        [minimal corrected version - change only what's broken]
        ```
        REASONING: [brief explanation of the minimal change]
        
        IF UPGRADE_STATUS: NEEDS_MORE_INFO
        MISSING_INFO: [what additional information is needed]
        
        IF UPGRADE_STATUS: NO_SOLUTION
        REASON: [why no solution can be found]
        """

        try:
            llm_start_time = time.time()
            self.logger.info("🤖 STEP 4A: SENDING COMPLETE CONTEXT TO LLM")
            self.logger.info("─" * 80)
            self.logger.info("📝 COMPLETE PROMPT BEING SENT:")
            self.logger.info(prompt)
            self.logger.info("─" * 80)
            self.logger.info("⏳ Waiting for LLM response...")

            response = self.llm.invoke(prompt)
            plan_text = response.content
            llm_time = time.time() - llm_start_time

            self.logger.info(f"🤖 LLM response received in {llm_time:.2f}s")
            self.logger.info("─" * 80)
            self.logger.info("📝 COMPLETE LLM RESPONSE:")
            self.logger.info(plan_text)
            self.logger.info("─" * 80)

            # Parse the LLM response
            self.logger.info("🔧 PARSING LLM RESPONSE:")
            upgrade_plan = self._parse_upgrade_plan(plan_text)
            self.logger.info(
                f"   📊 Parsed Status: {upgrade_plan.get('status', 'Unknown')}"
            )
            if upgrade_plan.get("before_code"):
                self.logger.info("   📝 Before Code Extracted:")
                self.logger.info(f"      {upgrade_plan['before_code']}")
            if upgrade_plan.get("after_code"):
                self.logger.info("   ✨ After Code Extracted:")
                self.logger.info(f"      {upgrade_plan['after_code']}")
            if upgrade_plan.get("reasoning"):
                self.logger.info(f"   🧠 Reasoning: {upgrade_plan['reasoning']}")

            state["migration_plan"] = upgrade_plan

            # Extract before/after code if available
            if upgrade_plan.get("status") == "READY":
                state["before_code"] = upgrade_plan.get("before_code")
                state["after_code"] = upgrade_plan.get("after_code")
                self.logger.info(
                    "✅ STEP 4A COMPLETE: New working code determined - ready to apply changes"
                )
                self.logger.info("🔧 CODE CHANGES TO BE APPLIED:")
                self.logger.info(
                    f"   📝 Will replace: {len(state['before_code'])} characters"
                )
                self.logger.info(
                    f"   ✨ Will add: {len(state['after_code'])} characters"
                )
            elif upgrade_plan.get("status") == "NEEDS_MORE_INFO":
                self.logger.warning(
                    f"� Need more documentation: {upgrade_plan.get('missing_info', 'Unknown')}"
                )
            else:
                self.logger.warning(
                    f"❌ No solution found: {upgrade_plan.get('reason', 'Unknown')}"
                )

            plan_time = time.time() - node_start_time
            self.logger.info(
                f"📋 Upgrade plan status: {upgrade_plan.get('status', 'UNKNOWN')}"
            )
            self.logger.info(f"⏱️ Step 4A completed in {plan_time:.2f}s")

        except Exception as e:
            plan_time = time.time() - node_start_time
            self.logger.error(f"❌ Failed to create upgrade plan: {e}")
            self.logger.error(f"💥 Planning failed after {plan_time:.2f}s")
            state["migration_plan"] = {"status": "NO_SOLUTION", "reason": str(e)}

        log_workflow_progress(self.logger, state)
        return state

    def apply_code_changes(self, state: NotebookUpgradeState) -> NotebookUpgradeState:
        """STEP 4B: Update the broken code cell with the new working code."""
        node_start_time = time.time()
        self.current_node = "apply_changes"

        log_state_transition(self.logger, "plan_upgrade", "apply_changes", state)
        self.logger.info("🔧 STEP 4B: UPDATING BROKEN CODE CELL WITH NEW WORKING CODE")
        self.logger.info("📝 Applying planned code changes to notebook...")

        before_code = state.get("before_code")
        after_code = state.get("after_code")

        if not before_code or not after_code:
            self.logger.error(
                "❌ Missing before_code or after_code - cannot apply changes"
            )
            state["upgrade_status"] = "failed"
            return state

        self.logger.info(f"📝 Before code: {len(before_code)} characters")
        self.logger.info(f"📝 After code: {len(after_code)} characters")
        self.logger.debug(f"🔍 Before snippet: {before_code}")
        self.logger.debug(f"🔍 After snippet: {after_code}")

        # Apply the changes using the edit tool
        edit_start_time = time.time()
        edit_result = self.tools["notebook_edit"]._run(
            state["notebook_path"], before_code, after_code
        )
        edit_time = time.time() - edit_start_time

        log_tool_execution(
            self.logger,
            "notebook_edit",
            {
                "notebook_path": state["notebook_path"],
                "before_code_length": len(before_code),
                "after_code_length": len(after_code),
            },
            edit_result,
            edit_time,
        )

        if "✅ Successfully" in edit_result:
            self.logger.info("✅ STEP 4B COMPLETE: Code changes applied successfully")
            state["upgrade_status"] = "applied"
        else:
            self.logger.error(f"❌ Failed to apply changes: {edit_result}")
            state["upgrade_status"] = "failed"

        apply_time = time.time() - node_start_time
        self.logger.info(f"⏱️ Step 4B completed in {apply_time:.2f}s")
        log_workflow_progress(self.logger, state)
        return state

    def validate_notebook_fix(
        self, state: NotebookUpgradeState
    ) -> NotebookUpgradeState:
        """STEP 5: Retest notebook to verify the fix and iterate if needed."""
        node_start_time = time.time()
        self.current_node = "validate_fix"

        log_state_transition(self.logger, "apply_changes", "validate_fix", state)
        self.logger.info("🧪 STEP 5: RETESTING NOTEBOOK TO VERIFY FIX")
        self.logger.info("✅ Re-executing notebook to validate the applied changes...")

        validation_start_time = time.time()
        validation_result = self.tools["notebook_execution"]._run(
            state["notebook_path"]
        )
        validation_time = time.time() - validation_start_time

        log_tool_execution(
            self.logger,
            "notebook_execution_validation",
            {"notebook_path": state["notebook_path"]},
            validation_result,
            validation_time,
        )

        if "✅ SUCCESS" in validation_result:
            self.logger.info(
                "🎉 STEP 5 COMPLETE: Validation successful - notebook now works!"
            )
            self.logger.info("✅ ALL ERRORS RESOLVED - No further iterations needed")
            state["upgrade_status"] = "success"
        else:
            self.logger.warning(
                "🔄 STEP 5: Validation failed - notebook still has issues"
            )
            self.logger.info(
                "🔄 ITERATION REQUIRED: Proceeding to next cycle for remaining errors"
            )
            state["upgrade_status"] = "retry"
            state["execution_error"] = validation_result
            state["iteration_count"] += 1

        total_validation_time = time.time() - node_start_time
        self.logger.info(f"⏱️ Step 5 completed in {total_validation_time:.2f}s")
        log_workflow_progress(self.logger, state)
        return state

    def finalize_upgrade_results(
        self, state: NotebookUpgradeState
    ) -> NotebookUpgradeState:
        """Finalize the upgrade process and prepare results."""
        node_start_time = time.time()
        self.current_node = "finalize_results"

        log_state_transition(self.logger, "validate_fix", "finalize_results", state)
        self.logger.info("📊 Finalizing upgrade process and preparing results...")

        # Calculate total workflow time
        total_workflow_time = (
            time.time() - self.workflow_start_time if self.workflow_start_time else 0
        )

        # Prepare final results
        final_result = {
            "notebook_path": state["notebook_path"],
            "success": state["upgrade_status"] == "success",
            "iterations": state["iteration_count"],
            "final_status": state["upgrade_status"],
            "backup_paths": state["backup_paths"],
            "total_time": total_workflow_time,
            "timestamp": datetime.now().isoformat(),
        }

        # Add error details if failed
        if state["upgrade_status"] != "success":
            final_result["error_details"] = state.get("error_details", {})
            final_result["last_execution_error"] = state.get("execution_error", "")

        state["final_result"] = final_result

        # Save results to file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_path = f"{state['notebook_path']}.upgrade_results_{timestamp}.json"
        try:
            with open(results_path, "w") as f:
                json.dump(final_result, f, indent=2)
            self.logger.info(f"📁 Results saved to: {results_path}")
        except Exception as e:
            self.logger.error(f"❌ Failed to save results: {e}")

        # Final summary logging
        self.logger.info("=" * 60)
        self.logger.info("📋 FINAL UPGRADE SUMMARY")
        self.logger.info("=" * 60)
        self.logger.info(f"📁 Notebook: {final_result['notebook_path']}")
        self.logger.info(f"✅ Success: {final_result['success']}")
        self.logger.info(f"🔄 Iterations: {final_result['iterations']}")
        self.logger.info(f"📊 Final Status: {final_result['final_status']}")
        self.logger.info(f"⏱️ Total Time: {final_result['total_time']:.2f}s")
        self.logger.info(f"📁 Backups: {len(final_result.get('backup_paths', []))}")

        if final_result["success"]:
            self.logger.info("🎉 UPGRADE COMPLETED SUCCESSFULLY!")
        else:
            self.logger.warning("😞 UPGRADE COMPLETED WITH ISSUES")
            if final_result.get("error_details"):
                error_type = final_result["error_details"].get("error_type", "Unknown")
                self.logger.warning(f"🐛 Last Error Type: {error_type}")

        finalize_time = time.time() - node_start_time
        self.logger.info(
            f"✅ finalize_upgrade_results completed in {finalize_time:.2f}s"
        )
        self.logger.info("=" * 60)

        return state

    def try_direct_llm_fix(self, state: NotebookUpgradeState) -> NotebookUpgradeState:
        """STEP 2.5: Try to fix the error using LLM's training data (no RAG needed)."""
        node_start_time = time.time()
        self.current_node = "try_direct_fix"

        log_state_transition(self.logger, "analyze_errors", "try_direct_fix", state)
        self.logger.info("🤖 STEP 2.5: TRYING DIRECT LLM FIX (NO RAG)")
        self.logger.info(
            "📋 Attempting to fix common Python errors using LLM's training data..."
        )

        try:
            error_details = state.get("error_details", {})
            failing_code = error_details.get("failing_code", "")
            error_message = state.get("execution_error", "")

            # Build prompt for direct fix without RAG context
            prompt = f"""
        You are an expert Python developer. Fix this code error using your training knowledge ONLY.
        
        FAILING CODE:
        ```python
        {failing_code}
        ```
        
        ERROR: {error_message}
        
        INSTRUCTIONS:
        1. Make the SMALLEST possible change to fix the error
        2. For basic Python errors (imports, syntax, etc.), fix directly
        3. Keep the same variable names and structure
        4. Only change what's broken - don't add extra complexity
        
        Provide your response in this EXACT format:
        
        FIX_STATUS: [READY | ATOTI_SPECIFIC | NO_SOLUTION]
        
        IF FIX_STATUS: READY
        BEFORE_CODE:
        ```python
        # ==BEFORE==
        {failing_code}
        ```
        AFTER_CODE:
        ```python
        # ==AFTER==
        [minimal corrected version - change only what's broken]
        ```
        REASONING: [brief explanation of the minimal change]
        
        IF FIX_STATUS: ATOTI_SPECIFIC
        REASON: [why this needs atoti-specific documentation]
        
        IF FIX_STATUS: NO_SOLUTION
        REASON: [why no solution can be found]
        """

            llm_start_time = time.time()
            self.logger.info("🤖 SENDING DIRECT FIX REQUEST TO LLM")
            self.logger.info("⏳ Waiting for LLM response...")

            response = self.llm.invoke(prompt)
            fix_text = response.content
            llm_time = time.time() - llm_start_time

            self.logger.info(f"🤖 LLM response received in {llm_time:.2f}s")
            self.logger.info("📝 COMPLETE LLM RESPONSE:")
            self.logger.info(fix_text)

            # Parse the direct fix response
            direct_fix = self._parse_direct_fix(fix_text)
            state["direct_fix_result"] = direct_fix

            self.logger.info("🔧 PARSING DIRECT FIX RESPONSE:")
            self.logger.info(f"   📊 Parsed Status: {direct_fix.get('status', 'None')}")
            self.logger.info(
                f"   📝 Before Code Found: {'Yes' if direct_fix.get('before_code') else 'No'}"
            )
            self.logger.info(
                f"   ✨ After Code Found: {'Yes' if direct_fix.get('after_code') else 'No'}"
            )

            if direct_fix.get("status") == "READY":
                # Store the fix for application
                state["before_code"] = direct_fix.get("before_code")
                state["after_code"] = direct_fix.get("after_code")
                state["migration_plan"] = {
                    "status": "READY",
                    "before_code": direct_fix.get("before_code"),
                    "after_code": direct_fix.get("after_code"),
                    "reasoning": direct_fix.get("reasoning"),
                    "fix_type": "direct_llm",
                }
                self.logger.info(
                    "✅ STEP 2.5 COMPLETE: Direct fix ready - proceeding to apply"
                )
            elif direct_fix.get("status") == "ATOTI_SPECIFIC":
                self.logger.info(
                    "🔍 STEP 2.5: Atoti-specific error detected - will use RAG search"
                )
            else:
                self.logger.warning("❌ STEP 2.5: No direct solution found")

            direct_fix_time = time.time() - node_start_time
            self.logger.info(f"⏱️ Step 2.5 completed in {direct_fix_time:.2f}s")

        except Exception as e:
            self.logger.error(f"❌ Direct fix failed: {e}")
            state["direct_fix_result"] = {"status": "NO_SOLUTION", "reason": str(e)}

        log_workflow_progress(self.logger, state)
        return state

    # Routing Functions (Conditional Logic)

    def route_after_error_analysis(self, state: NotebookUpgradeState) -> str:
        """Route after error analysis to decide: direct LLM fix vs RAG search."""
        error_msg = state.get("execution_error", "").lower()

        # Check for common Python errors that don't need atoti documentation
        common_python_errors = [
            "name 'pd' is not defined",
            "name 'np' is not defined",
            "name 'plt' is not defined",
            "importerror:",
            "modulenotfounderror:",
            "indentationerror:",
            "syntaxerror:",
            "nameerror:",
            "typeerror:",
            "keyerror:",
            "indexerror:",
            "attributeerror: 'nonetype'",
        ]

        # Check for atoti-specific errors that need RAG
        atoti_specific_errors = [
            "tt.create_session",
            "tt.session(",
            "atoti",
            "session.create_cube",
            "session.read_csv",
            "cube.hierarchies",
            "cube.levels",
            "cube.measures",
        ]

        self.logger.info("🤔 ANALYZING ERROR TYPE FOR ROUTING DECISION:")
        self.logger.info(f"   📝 Error excerpt: {error_msg[:100]}...")

        # Check for basic Python errors first
        for python_error in common_python_errors:
            if python_error in error_msg:
                self.logger.info(f"   🐍 Detected common Python error: {python_error}")
                self.logger.info(
                    "   🎯 ROUTING: direct_fix (try LLM training data first)"
                )
                return "direct_fix"

        # Check for atoti-specific errors
        for atoti_error in atoti_specific_errors:
            if atoti_error in error_msg:
                self.logger.info(f"   📚 Detected atoti-specific error: {atoti_error}")
                self.logger.info("   🎯 ROUTING: rag_search (need atoti documentation)")
                return "rag_search"

        # Default to direct fix for unknown errors (try LLM first)
        self.logger.info("   ❓ Unknown error type - trying direct fix first")
        self.logger.info("   🎯 ROUTING: direct_fix (fallback to LLM training)")
        return "direct_fix"

    def route_after_direct_fix(self, state: NotebookUpgradeState) -> str:
        """Route after direct LLM fix attempt."""
        # Check both direct_fix_result and migration_plan since they may be stored differently
        fix_result = state.get("direct_fix_result", {})
        migration_plan = state.get("migration_plan", {})

        # Use migration_plan status if direct_fix_result is empty (LangGraph state issue)
        fix_status = fix_result.get("status") or migration_plan.get(
            "status", "NO_SOLUTION"
        )

        self.logger.info(f"🔀 Routing after direct fix: status={fix_status}")
        self.logger.info(f"🔍 direct_fix_result: {fix_result}")
        self.logger.info(f"🔍 migration_plan: {migration_plan}")

        if fix_status == "READY":
            self.logger.info("✅ Direct fix successful - applying changes")
            return "apply"
        elif fix_status == "ATOTI_SPECIFIC":
            self.logger.info(
                "🔍 LLM detected atoti-specific error - falling back to RAG search"
            )
            return "rag_fallback"
        else:
            self.logger.warning("❌ Direct fix failed - no solution")
            return "no_solution"

    def route_after_search(self, state: NotebookUpgradeState) -> str:
        """Route based on RAG search results."""
        if state.get("search_attempts", 0) >= state.get("max_search_attempts", 3):
            self.logger.warning("🚨 Maximum search attempts reached")
            return "max_search"
        else:
            return "plan"

    def route_after_execution(self, state: NotebookUpgradeState) -> str:
        """Route based on notebook execution results."""
        if "✅ SUCCESS" in state.get("execution_error", ""):
            return "success"
        elif state["iteration_count"] >= state["max_iterations"]:
            return "max_iterations"
        else:
            return "error"

    def route_after_planning(self, state: NotebookUpgradeState) -> str:
        """Route based on upgrade planning results with circuit breaker logic."""
        plan_status = state.get("migration_plan", {}).get("status", "NO_SOLUTION")

        self.logger.info(
            f"🔀 Routing after planning: status={plan_status}, search_attempts={state.get('search_attempts', 0)}, planning_attempts={state.get('planning_attempts', 0)}"
        )

        # Priority 1: If we have a ready plan, apply it regardless of circuit breakers
        if plan_status == "READY":
            self.logger.info(
                "✅ Plan ready - proceeding to apply changes (overriding circuit breakers)"
            )
            return "apply"

        # Priority 2: Circuit breaker checks for non-ready plans
        if state.get("upgrade_status") == "failed":
            self.logger.warning("🚨 Circuit breaker activated - routing to finalize")
            return "no_solution"

        if state.get("search_attempts", 0) >= state.get("max_search_attempts", 3):
            self.logger.warning(
                "🚨 Maximum search attempts reached - routing to finalize"
            )
            return "no_solution"

        if state.get("planning_attempts", 0) >= state.get("max_planning_attempts", 3):
            self.logger.warning(
                "🚨 Maximum planning attempts reached - routing to finalize"
            )
            return "no_solution"

        # Priority 3: Other routing logic
        if plan_status == "NEEDS_MORE_INFO":
            # Only allow returning to search if we haven't exceeded limits
            if state.get("search_attempts", 0) < state.get("max_search_attempts", 3):
                self.logger.info(
                    "🔄 Need more info - returning to search (with limits)"
                )
                return "needs_more_info"
            else:
                self.logger.warning(
                    "⚠️ Need more info but search limit reached - giving up"
                )
                return "no_solution"
        else:
            self.logger.info("❌ No solution found - finalizing")
            return "no_solution"

    def route_after_validation(self, state: NotebookUpgradeState) -> str:
        """Route based on validation results with improved iteration tracking."""
        self.logger.info(
            f"🔀 Routing after validation: status={state['upgrade_status']}, iteration={state['iteration_count']}/{state['max_iterations']}"
        )

        if state["upgrade_status"] == "success":
            self.logger.info("🎉 Validation successful - finalizing")
            return "success"
        elif state["iteration_count"] >= state["max_iterations"]:
            self.logger.warning(
                f"⚠️ Maximum iterations ({state['max_iterations']}) reached - finalizing"
            )
            return "max_iterations"
        else:
            # Reset circuit breaker counters for next iteration
            state["search_attempts"] = 0
            state["planning_attempts"] = 0
            self.logger.info(
                f"🔄 Validation failed - starting iteration {state['iteration_count'] + 1} (circuit breakers reset)"
            )
            return "retry"

    # Utility Functions

    def _extract_error_type(self, error_msg: str) -> str:
        """Extract error type from error message."""
        error_patterns = [
            r"(\w+Error):",
            r"(\w+Exception):",
            r"(\w+Error)\s",
            r"(\w+Exception)\s",
        ]

        for pattern in error_patterns:
            match = re.search(pattern, error_msg)
            if match:
                return match.group(1)
        return "UnknownError"

    def _extract_error_message(self, error_msg: str) -> str:
        """Extract the core error message."""
        lines = error_msg.split("\n")
        for line in lines:
            if "Error:" in line or "Exception:" in line or "AttributeError" in line:
                return line.strip()
        return "Unknown error message"

    def _extract_failing_code(self, error_msg: str) -> str:
        """Extract the failing code from error message."""
        # Look for code between dashes
        if "------------------" in error_msg:
            parts = error_msg.split("------------------")
            if len(parts) >= 3:
                code_part = parts[1].strip()
                return code_part

        # Look for patterns that indicate code content
        if "import atoti" in error_msg and "session = tt.create_session()" in error_msg:
            return "import atoti as tt\n\nsession = tt.create_session()"
        return ""

    def _parse_upgrade_plan(self, plan_text: str) -> Dict[str, Any]:
        """Parse the LLM response into a structured upgrade plan."""
        plan = {}

        # Extract status
        status_match = re.search(r"UPGRADE_STATUS:\s*(\w+)", plan_text)
        if status_match:
            plan["status"] = status_match.group(1)

        # Extract before code
        before_match = re.search(
            r"BEFORE_CODE:\s*```python\s*# ==BEFORE==\s*(.*?)\s*```",
            plan_text,
            re.DOTALL,
        )
        if before_match:
            plan["before_code"] = before_match.group(1).strip()

        # Extract after code
        after_match = re.search(
            r"AFTER_CODE:\s*```python\s*# ==AFTER==\s*(.*?)\s*```", plan_text, re.DOTALL
        )
        if after_match:
            plan["after_code"] = after_match.group(1).strip()

        # Extract reasoning
        reasoning_match = re.search(
            r"REASONING:\s*(.*?)(?:\n\n|\Z)", plan_text, re.DOTALL
        )
        if reasoning_match:
            plan["reasoning"] = reasoning_match.group(1).strip()

        return plan

    def _parse_direct_fix(self, fix_text: str) -> Dict[str, Any]:
        """Parse the direct LLM fix response into a structured result."""
        fix = {}

        # Extract status
        status_match = re.search(r"FIX_STATUS:\s*(\w+)", fix_text)
        if status_match:
            fix["status"] = status_match.group(1)

        # Extract before code
        before_match = re.search(
            r"BEFORE_CODE:\s*```python\s*# ==BEFORE==\s*(.*?)\s*```",
            fix_text,
            re.DOTALL,
        )
        if before_match:
            fix["before_code"] = before_match.group(1).strip()

        # Extract after code
        after_match = re.search(
            r"AFTER_CODE:\s*```python\s*# ==AFTER==\s*(.*?)\s*```", fix_text, re.DOTALL
        )
        if after_match:
            fix["after_code"] = after_match.group(1).strip()

        # Extract reasoning or reason
        reasoning_match = re.search(
            r"REASONING:\s*(.*?)(?:\n\n|\Z)", fix_text, re.DOTALL
        )
        if reasoning_match:
            fix["reasoning"] = reasoning_match.group(1).strip()
        else:
            reason_match = re.search(r"REASON:\s*(.*?)(?:\n\n|\Z)", fix_text, re.DOTALL)
            if reason_match:
                fix["reason"] = reason_match.group(1).strip()

        return fix


def main():
    """Main function to demonstrate the LangGraph 5-step notebook upgrade system."""
    print("🚀 Starting LangGraph Notebook Upgrade System")
    print("=" * 60)
    print("🔄 5-STEP ITERATIVE WORKFLOW:")
    print("1. Test Notebook → Execute to analyze errors")
    print("2. Analyze Error → Extract details for RAG queries")
    print("3. RAG Search → Find solutions in documentation")
    print("4. Plan & Apply Fix → Update broken code cells")
    print("5. Validate & Iterate → Retest until all errors resolved")
    print("=" * 60)

    # Initialize the upgrade workflow
    print("🔧 Initializing upgrade workflow...")
    upgrader = NotebookUpgradeWorkflow()

    # Use the actual notebook with the known error - tt.create_session()
    notebook_path = "/Users/aya/Desktop/atoti/02-technical-guides/multidimensional-analysis/main.ipynb"

    print(f"\n🎯 Target notebook: {notebook_path}")
    print("🔄 Starting 5-step upgrade process with max 3 iterations...")
    print("=" * 60)

    start_time = time.time()
    results = upgrader.upgrade_notebook(notebook_path, max_iterations=3)
    total_time = time.time() - start_time

    # Enhanced summary with more details
    print("\n" + "=" * 60)
    print("📋 FINAL UPGRADE SUMMARY")
    print("=" * 60)
    print(f"📁 Notebook: {results['notebook_path']}")
    print(f"✅ Success: {results['success']}")
    print(f"🔄 Iterations: {results.get('iterations', 'N/A')}")
    print(f"📊 Status: {results.get('final_status', 'Unknown')}")
    print(f"⏱️  Total Time: {results.get('total_time', total_time):.2f}s")

    if results.get("backup_paths"):
        print(f"📁 Backups Created: {len(results['backup_paths'])}")

    print("=" * 60)

    if results["success"]:
        print("🎉 Notebook has been successfully upgraded!")
        print("✅ The 5-step workflow resolved all errors.")
    else:
        print("😞 Notebook upgrade failed.")
        print(
            "📋 Check the detailed logs above and the saved results file for more information."
        )
        if results.get("error"):
            print(f"❌ Last Error: {results['error']}")

    print(f"\n📊 5-step workflow completed in {total_time:.2f} seconds")
    return results


if __name__ == "__main__":
    main()
