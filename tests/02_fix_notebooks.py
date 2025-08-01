#!/usr/bin/env python3
"""
CrewAI Agentic Flow for Jupyter Notebook Fixing using RAG and Ollama Devstral

This system creates a multi-agent workflow that:
1. Analyzes notebook failures using RAG from your vectordb
2. Fixes issues using Ollama's Devstral model
3. Iteratively tests and improves until issues are resolved
4. Uses fully open-source tools (CrewAI + Ollama + ChromaDB)
"""

import json
import subprocess
from typing import Dict, Any
from datetime import datetime

# Configuration constants
NOTEBOOK_EXECUTION_TIMEOUT = 120  # seconds
NOTEBOOK_EXECUTION_CELL_TIMEOUT = 60  # seconds
MAX_ERROR_CONTEXT_LINES = 40
MAX_RAW_ERROR_LINES = 30
MAX_FILE_CONTENT_PREVIEW = 2000  # characters

# CrewAI imports
try:
    from crewai import Agent, Task, Crew, Process
    from crewai.tools import BaseTool

    CREWAI_AVAILABLE = True
except ImportError:
    print("❌ CrewAI not available. Install with: uv add crewai")
    CREWAI_AVAILABLE = False

# RAG and Vector DB imports
try:
    from langchain_ollama import OllamaEmbeddings, ChatOllama
    from langchain_chroma import Chroma

    RAG_AVAILABLE = True
except ImportError:
    print(
        "❌ RAG dependencies not available. Install with: pip install langchain-ollama langchain-chroma"
    )
    RAG_AVAILABLE = False


class NotebookExecutionTool(BaseTool):
    """Tool for executing notebook cells and capturing output."""

    name: str = "notebook_execution"
    description: str = (
        "Execute a Jupyter notebook and return the output or error. "
        "Use the exact notebook file path as the notebook_path parameter. "
        "This will execute the entire notebook."
    )

    def _run(self, notebook_path: str) -> str:
        """Execute a notebook and return results."""
        try:
            # Use nbconvert to execute the notebook - it will stop at first error
            result = subprocess.run(
                [
                    "uv",
                    "run",
                    "jupyter",
                    "nbconvert",
                    "--to",
                    "notebook",
                    "--execute",
                    f"--ExecutePreprocessor.timeout={NOTEBOOK_EXECUTION_CELL_TIMEOUT}",
                    "--output",
                    f"{notebook_path}.executed",
                    notebook_path,
                ],
                capture_output=True,
                text=True,
                timeout=NOTEBOOK_EXECUTION_TIMEOUT,
            )

            if result.returncode == 0:
                return "✅ SUCCESS: Notebook executed successfully without errors"
            else:
                # Extract error information neutrally without categorization
                error_msg = result.stderr

                # Look for the cell error section for better context
                lines = error_msg.split("\n")
                error_context = []
                cell_content = []
                capturing_cell = False
                capturing_error = False

                for line in lines:
                    # Look for cell execution markers
                    if "An error occurred while executing the following cell:" in line:
                        capturing_cell = True
                        error_context.append("=== ERROR IN CELL ===")
                        continue

                    # Capture the cell content
                    if capturing_cell and line.strip().startswith("--"):
                        if not cell_content:
                            # Start capturing cell content
                            continue
                        else:
                            # End of cell content
                            capturing_cell = False
                            capturing_error = True
                            error_context.extend(
                                ["Cell content:"]
                                + cell_content
                                + ["", "=== ERROR MESSAGE ==="]
                            )
                            continue

                    if capturing_cell:
                        cell_content.append(line.strip())

                    # Capture error traceback
                    if capturing_error:
                        error_context.append(line.strip())
                        # Stop after reasonable amount of error info
                        if len(error_context) > MAX_ERROR_CONTEXT_LINES:
                            break

                # If we didn't capture structured error, show raw stderr
                if not error_context:
                    error_context = ["=== RAW ERROR OUTPUT ==="] + error_msg.split(
                        "\n"
                    )[:MAX_RAW_ERROR_LINES]

                result_text = "\n".join(error_context)
                return f"❌ EXECUTION FAILED: Notebook stopped due to error\n\n{result_text}"

        except subprocess.TimeoutExpired:
            return f"❌ Execution timed out after {NOTEBOOK_EXECUTION_TIMEOUT // 60} minutes"
        except Exception as e:
            return f"❌ Execution error: {str(e)}"


class NotebookAnalysisTool(BaseTool):
    """Tool for analyzing notebook structure and identifying problematic cells based on execution errors."""

    name: str = "notebook_analysis"
    description: str = (
        "Analyze a Jupyter notebook to identify the problematic cell based on execution errors. "
        "Takes execution_error_output (from notebook_execution tool) and notebook_path to identify "
        "which specific cell is causing the error."
    )

    def _run(self, notebook_path: str, execution_error_output: str = None) -> str:
        """Analyze notebook and identify problematic cell based on execution errors."""
        try:
            import nbformat

            # Read the notebook using nbformat
            with open(notebook_path, "r", encoding="utf-8") as f:
                notebook = nbformat.read(f, as_version=4)

            # Find all code cells
            code_cells = []
            cell_number = 1

            for cell in notebook.cells:
                if cell.cell_type == "code":
                    code_cells.append(
                        {
                            "number": cell_number,
                            "id": cell.get("id", "unknown"),
                            "source": cell.source.strip(),
                            "has_output": len(cell.get("outputs", [])) > 0,
                            "execution_count": cell.get("execution_count"),
                        }
                    )
                    cell_number += 1

            if not code_cells:
                return "❌ No code cells found in the notebook."

            # If no execution error provided, just return cell structure
            if not execution_error_output or "✅ SUCCESS" in execution_error_output:
                result = (
                    f"📋 Found {len(code_cells)} code cells (no errors detected):\n\n"
                )
                for cell_info in code_cells:
                    source_preview = (
                        cell_info["source"][:200] + "..."
                        if len(cell_info["source"]) > 200
                        else cell_info["source"]
                    )
                    result += f"Cell #{cell_info['number']}:\n```python\n{source_preview}\n```\n\n"
                return result

            # Parse execution error to identify the failing cell
            error_analysis = self._parse_execution_error(execution_error_output)
            failing_cell_number = self._identify_failing_cell(
                error_analysis, code_cells
            )

            # Compile simple analysis report
            result = "🔍 NOTEBOOK ERROR ANALYSIS\n"
            result += "=" * 40 + "\n\n"

            # Error summary
            result += f"❌ FAILING CELL: #{failing_cell_number}\n"
            result += f"🐛 ERROR TYPE: {error_analysis['error_type']}\n"
            result += f"💬 ERROR MESSAGE: {error_analysis['error_message']}\n\n"

            # Failing cell code
            result += f"📝 PROBLEMATIC CODE (Cell #{failing_cell_number}):\n"
            result += "```python\n"
            result += code_cells[failing_cell_number - 1]["source"]
            result += "\n```\n"

            return result

        except Exception as e:
            return f"❌ Analysis failed: {str(e)}"

    def _parse_execution_error(self, execution_output: str) -> dict:
        """Parse execution error output to extract key information."""
        error_info = {
            "cell_content": "",
            "error_message": "",
            "error_type": "",
            "full_traceback": [],
        }

        lines = execution_output.split("\n")
        capturing_cell = False
        capturing_error = False

        for line in lines:
            if "Cell content:" in line:
                capturing_cell = True
                continue
            elif "=== ERROR MESSAGE ===" in line:
                capturing_cell = False
                capturing_error = True
                continue

            if capturing_cell and line.strip():
                error_info["cell_content"] += line.strip() + "\n"
            elif capturing_error:
                error_info["full_traceback"].append(line.strip())
                # Look for error type patterns
                if ("Error:" in line or "Exception:" in line) and not error_info[
                    "error_type"
                ]:
                    error_info["error_type"] = line.strip()
                # Capture the most specific error message
                if (
                    line.strip()
                    and not line.startswith("File ")
                    and not line.startswith("  ")
                ):
                    if "Error:" in line or "Exception:" in line:
                        error_info["error_message"] = line.strip()

        # Fallback if we didn't get structured error info
        if not error_info["error_message"] and error_info["full_traceback"]:
            # Look for the last meaningful line in traceback
            for line in reversed(error_info["full_traceback"]):
                if line.strip() and ("Error" in line or "Exception" in line):
                    error_info["error_message"] = line.strip()
                    break

        return error_info

    def _identify_failing_cell(self, error_analysis: dict, code_cells: list) -> int:
        """Identify which code cell number failed based on error content."""
        cell_content = error_analysis["cell_content"].strip()

        if not cell_content:
            return 1  # Default to first cell if no content captured

        # Look for exact or partial matches
        best_match_score = 0
        best_match_cell = 1

        for i, cell in enumerate(code_cells):
            cell_source = cell["source"].strip()

            # Calculate match score
            if cell_content in cell_source:
                return i + 1  # Exact substring match
            elif cell_source in cell_content:
                return i + 1  # Cell is subset of error content
            else:
                # Calculate similarity by counting common lines
                cell_lines = set(
                    line.strip() for line in cell_source.split("\n") if line.strip()
                )
                error_lines = set(
                    line.strip() for line in cell_content.split("\n") if line.strip()
                )
                common_lines = len(cell_lines.intersection(error_lines))

                if common_lines > best_match_score:
                    best_match_score = common_lines
                    best_match_cell = i + 1

        return best_match_cell


class NotebookEditTool(BaseTool):
    """Tool for editing notebook cells using nbformat for robust cell handling."""

    name: str = "notebook_edit"
    description: str = (
        "Edit a notebook cell using analysis output from the analyzer agent. "
        "Requires notebook_path and analysis_output (from analyzer agent). "
        "Automatically extracts the failing cell number and recommended code from the analysis."
    )

    def _run(self, notebook_path: str, analysis_output: str) -> str:
        """Edit a notebook cell using analysis output to determine cell and code."""
        try:
            import nbformat

            # Extract cell number from analysis output
            cell_number = self._extract_failing_cell_from_analysis(analysis_output)
            if cell_number is None:
                # Provide more detailed error information
                return f"❌ Could not extract failing cell number from analysis output. Analysis output preview: {analysis_output[:500]}..."

            # Extract recommended code from analysis output
            new_content = self._extract_fixed_code_from_analysis(analysis_output)
            if new_content is None:
                return f"❌ Could not extract FIXED_CODE from analysis output. Cell number found: {cell_number}. Analysis output preview: {analysis_output[:500]}..."

            # Read the notebook using nbformat
            with open(notebook_path, "r", encoding="utf-8") as f:
                notebook = nbformat.read(f, as_version=4)

            # Find code cells only (skip markdown cells in numbering)
            code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]

            if cell_number < 1 or cell_number > len(code_cells):
                return f"❌ Cell number {cell_number} is out of range. Found {len(code_cells)} code cells."

            # Get the target cell (convert 1-based to 0-based indexing)
            target_cell = code_cells[cell_number - 1]

            # Update the cell content
            target_cell.source = new_content

            # Clear any previous outputs and execution count
            target_cell.outputs = []
            target_cell.execution_count = None

            # Save the notebook back using nbformat
            with open(notebook_path, "w", encoding="utf-8") as f:
                nbformat.write(notebook, f)

            return f"✅ Successfully edited code cell #{cell_number} (ID: {target_cell.get('id', 'unknown')})"

        except Exception as e:
            return f"❌ Edit failed: {str(e)}"

    def _extract_failing_cell_from_analysis(self, analysis_output: str) -> int:
        """Extract the failing cell number from analyzer agent output."""
        import re

        # Look for "CELL_NUMBER: X" pattern from analyzer agent output
        match = re.search(r"CELL_NUMBER:\s*(\d+)", analysis_output)
        if match:
            return int(match.group(1))

        # Fallback: look for "FAILING CELL: #X" pattern from analysis tool output
        match = re.search(r"❌ FAILING CELL: #(\d+)", analysis_output)
        if match:
            return int(match.group(1))

        # Additional fallback: look for other Cell patterns
        match = re.search(r"Cell #(\d+)", analysis_output)
        if match:
            return int(match.group(1))

        return None

    def _extract_fixed_code_from_analysis(self, analysis_output: str) -> str:
        """Extract the FIXED_CODE from analyzer output."""
        import re

        # Look for FIXED_CODE: followed by code block
        pattern = r"FIXED_CODE:\s*```python\s*(.*?)\s*```"
        match = re.search(pattern, analysis_output, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Fallback: look for any code block after FIXED_CODE
        pattern = r"FIXED_CODE:\s*(.*?)(?=\n\n|\n[A-Z]|$)"
        match = re.search(pattern, analysis_output, re.DOTALL)
        if match:
            code = match.group(1).strip()
            # Remove markdown code block markers if present
            code = re.sub(r"^```python\s*", "", code)
            code = re.sub(r"\s*```$", "", code)
            return code.strip()

        return None


class FileReadTool(BaseTool):
    """Simple tool for reading files."""

    name: str = "file_read"
    description: str = "Read the contents of a file. Use file_path parameter with the complete file path."

    def _run(self, file_path: str) -> str:
        """Read file contents."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if len(content) > MAX_FILE_CONTENT_PREVIEW:
                return f"File contents of {file_path}:\n{content[:MAX_FILE_CONTENT_PREVIEW]}..."
            else:
                return f"File contents of {file_path}:\n{content}"
        except Exception as e:
            return f"❌ Failed to read file: {str(e)}"


class DirectoryReadTool(BaseTool):
    """Simple tool for listing directory contents."""

    name: str = "directory_read"
    description: str = "List the contents of a directory. Use directory_path parameter with the complete directory path."

    def _run(self, directory_path: str) -> str:
        """List directory contents."""
        try:
            import os

            contents = os.listdir(directory_path)
            return f"Directory contents of {directory_path}:\n" + "\n".join(contents)
        except Exception as e:
            return f"❌ Failed to read directory: {str(e)}"


class RAGSearchTool(BaseTool):
    """Tool for searching the atoti documentation vectordb."""

    name: str = "rag_search"
    description: str = (
        "Search the atoti documentation using RAG to find relevant information. "
        "Use 'query' parameter for the search text. Returns top 5 most relevant documents."
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
            print(f"✅ RAG system initialized with vectordb at {self._vectordb_path}")
        except Exception as e:
            print(f"❌ Failed to initialize RAG: {e}")

    def _run(self, query: str) -> str:
        """Search the vectordb for relevant documentation."""
        if not self._vectordb:
            return "❌ RAG system not initialized"

        try:
            # Use fixed k=5 to avoid parameter validation issues
            docs = self._vectordb.similarity_search(query, k=5)
            if not docs:
                return "❌ No relevant documentation found"

            context = "\n\n".join(
                [f"Document {i + 1}:\n{doc.page_content}" for i, doc in enumerate(docs)]
            )

            return f"📚 Found {len(docs)} relevant documents:\n\n{context}"
        except Exception as e:
            return f"❌ RAG search failed: {e}"


class NotebookFixerCrew:
    """CrewAI-based notebook fixing system with RAG and iterative improvement."""

    def __init__(
        self, vectordb_path: str = "/Users/aya/Desktop/atoti/atoti_docs_vectordb"
    ):
        self.vectordb_path = vectordb_path
        self.llm = None
        self.crew = None
        self.tools = []
        self._initialize_llm()
        self._initialize_tools()
        self._create_agents()
        # Tasks and crew will be created in fix_notebook method with specific notebook path

    def _initialize_llm(self):
        """Initialize Ollama Devstral model."""
        try:
            self.llm = ChatOllama(
                model="ollama/devstral:latest",  # Use ollama/ prefix for LiteLLM compatibility
                temperature=0.1,
                base_url="http://localhost:11434",
            )
            print("✅ Devstral model initialized")

            # Test the LLM connection
            try:
                test_response = self.llm.invoke("Hello, are you working?")
                print(
                    f"🔗 LLM connection test successful: {test_response.content[:50]}..."
                )
            except Exception as test_e:
                print(f"⚠️ LLM connection test failed: {test_e}")

        except Exception as e:
            print(f"❌ Failed to initialize Devstral: {e}")
            # Fallback to mistral if devstral is not available
            try:
                self.llm = ChatOllama(
                    model="ollama/mistral:latest",  # Use ollama/ prefix for LiteLLM compatibility
                    temperature=0.1,
                    base_url="http://localhost:11434",
                )
                print("✅ Fallback to Mistral model")

                # Test the fallback LLM connection
                try:
                    test_response = self.llm.invoke("Hello, are you working?")
                    print(
                        f"🔗 Fallback LLM connection test successful: {test_response.content[:50]}..."
                    )
                except Exception as test_e:
                    print(f"⚠️ Fallback LLM connection test failed: {test_e}")

            except Exception as e2:
                print(f"❌ Failed to initialize any Ollama model: {e2}")

    def _initialize_tools(self):
        """Initialize all tools for the agents."""
        self.tools = [
            NotebookExecutionTool(),
            NotebookAnalysisTool(),
            NotebookEditTool(),
            RAGSearchTool(self.vectordb_path),
            FileReadTool(),
            DirectoryReadTool(),
        ]
        print("✅ Tools initialized")

    def _create_agents(self):
        """Create specialized agents for the notebook fixing workflow."""

        # Create individual tool instances for each agent to avoid conflicts
        execution_tool = NotebookExecutionTool()
        analysis_tool = NotebookAnalysisTool()
        edit_tool = NotebookEditTool()
        rag_tool = RAGSearchTool(self.vectordb_path)
        file_read_tool = FileReadTool()

        self.analyzer_agent = Agent(
            role="Notebook Error Analyzer",
            goal="Analyze notebook execution errors and identify root causes",
            backstory="""You are an expert Python developer specializing in Jupyter notebooks and atoti.
            You can analyze execution errors, understand stack traces, and identify the specific issues
            that need to be fixed. You use RAG to search documentation for solutions.
            
            CRITICAL ROLE RESTRICTIONS:
            - You are an ANALYZER ONLY - you do NOT edit files or re-run notebooks
            - You ONLY execute notebooks once to capture errors, then analyze those errors
            - You do NOT update, modify, or re-execute notebooks after analysis
            - Your job ends with providing a fix recommendation in the required format
            - You work under manager supervision and can delegate to other agents when needed
            
            IMPORTANT: You focus ONLY on notebook files and atoti documentation. You do NOT read
            atoti source code files, library internals, or other Python modules. Your expertise
            is in understanding notebook execution and finding solutions in the atoti documentation.""",
            tools=[execution_tool, analysis_tool, rag_tool],
            llm=self.llm,
            verbose=True,
            allow_delegation=True,
        )

        self.fixer_agent = Agent(
            role="Code Fixer",
            goal="Execute the fix recommended by the analyzer by editing the correct cell and confirming the save",
            backstory="""You are a precise code editor focused ONLY on implementing fixes.
            Your job is simple execution:
            - Take the exact fix recommendations from the analyzer
            - Edit the notebook using the notebook_edit tool
            - Verify the save using the file_read tool
            
            You do NOT analyze, research, or make decisions about what to fix.
            The analyzer has already determined what needs to be fixed.
            You simply execute the exact instructions provided.
            You work under manager supervision and follow delegation instructions.
            
            CRITICAL: You work ONLY with notebook editing and file reading.
            You do NOT use RAG search or do any analysis.""",
            tools=[edit_tool, file_read_tool],
            llm=self.llm,
            verbose=True,
            allow_delegation=True,
        )

        self.validator_agent = Agent(
            role="Solution Validator",
            goal="Test fixes and ensure they work correctly",
            backstory="""You are a QA engineer who validates that fixes actually resolve the issues.
            You run tests, check outputs, and ensure the notebook executes successfully from start
            to finish without errors.
            You work under manager supervision and can provide feedback to other agents when needed.
            
            IMPORTANT: You focus ONLY on notebook execution and validation. You do NOT read
            atoti source code files, library internals, or other Python modules. Your role is
            to validate notebook execution and identify any remaining errors.""",
            tools=[execution_tool, file_read_tool],
            llm=self.llm,
            verbose=True,
            allow_delegation=True,
        )

        print("✅ Agents created")

        # Debug: Print tool information
        print(f"🔧 Fixer agent tools: {[tool.name for tool in self.fixer_agent.tools]}")
        print(
            f"🔧 Analyzer agent tools: {[tool.name for tool in self.analyzer_agent.tools]}"
        )
        print(
            f"🔧 Validator agent tools: {[tool.name for tool in self.validator_agent.tools]}"
        )

    def _create_tasks(self, notebook_path: str):
        """Create tasks for the notebook fixing workflow with specific notebook path."""

        self.analysis_task = Task(
            description=f"""Analyze the notebook and provide a fix recommendation.

            NOTEBOOK PATH: {notebook_path}
            
            TASK OVERVIEW: Analyze a failing Jupyter notebook to identify errors and provide fix recommendations.
            This task should be completed by the Notebook Error Analyzer agent.
            
            EXECUTION STEPS:
            1. Execute the notebook to capture errors
            2. Analyze the execution errors to identify the failing cell
            3. Search documentation for solutions using RAG
            4. Provide a structured fix recommendation
            
            REQUIRED OUTPUT FORMAT:
            CELL_NUMBER: [cell_number]
            FIXED_CODE: 
            ```python
            [exact corrected code for the cell]
            ```
            
            CONSTRAINTS:
            - Use exact path: {notebook_path}
            - Focus on the FIRST error found
            - Provide complete cell content, not partial fixes
            - Use varied RAG search strategies to find comprehensive solutions
            """,
            agent=self.analyzer_agent,
            expected_output="CELL_NUMBER and FIXED_CODE in the specified format for direct implementation",
        )

        self.fixing_task = Task(
            description=f"""Implement the fix recommended by the analyzer.

            NOTEBOOK PATH: {notebook_path}
            
            TASK OVERVIEW: Apply the exact fix provided by the analysis task to the notebook.
            This task should be completed by the Code Fixer agent.
            
            EXECUTION STEPS:
            1. Extract fix details from the analysis task output
            2. Edit the specified notebook cell with the recommended code
            3. Save the changes and confirm successful modification
            
            DEPENDENCIES:
            - Requires completion of the analysis task
            - Uses the CELL_NUMBER and FIXED_CODE from analysis output
            
            CONSTRAINTS:
            - Use exact path: {notebook_path}
            - Only edit the specified cell, do not modify other parts
            - Confirm save was successful before completing
            """,
            agent=self.fixer_agent,
            expected_output="Notebook edited and save confirmed, or clear error message if editing failed",
        )

        self.validation_task = Task(
            description=f"""Validate the implemented fix and confirm it works.

            NOTEBOOK PATH: {notebook_path}
            
            TASK OVERVIEW: Test the fixed notebook to ensure the errors are resolved.
            This task should be completed by the Solution Validator agent.
            
            EXECUTION STEPS:
            1. Execute the fixed notebook to check for errors
            2. Verify the notebook state and content
            3. Report success or identify any remaining issues
            
            DEPENDENCIES:
            - Requires completion of the fixing task
            - Validates the changes made by the Code Fixer agent
            
            SUCCESS CRITERIA:
            - Notebook executes without errors
            - All cells run successfully
            
            FAILURE HANDLING:
            - If errors remain, provide detailed analysis for next iteration
            - Identify specific error messages and locations
            
            CONSTRAINTS:
            - Use exact path: {notebook_path}
            - Focus only on execution validation
            """,
            agent=self.validator_agent,
            expected_output="Complete success confirmation OR detailed next error analysis for iteration",
        )

        print("✅ Tasks created")

    def _create_crew(self):
        """Create the CrewAI crew with hierarchical process and manager."""
        self.crew = Crew(
            agents=[self.analyzer_agent, self.fixer_agent, self.validator_agent],
            tasks=[self.analysis_task, self.fixing_task, self.validation_task],
            process=Process.hierarchical,
            manager_llm=self.llm,
            verbose=True,
        )
        print("✅ Crew created with hierarchical process and manager")

    def fix_notebook(
        self, notebook_path: str, max_iterations: int = 3
    ) -> Dict[str, Any]:
        """
        Fix a notebook with iterative improvement until it works or max iterations reached.

        Args:
            notebook_path: Path to the notebook to fix
            max_iterations: Maximum number of fix-test cycles

        Returns:
            Dictionary with results including success status and logs
        """
        if not CREWAI_AVAILABLE or not RAG_AVAILABLE:
            return {"error": "Required dependencies not available"}

        print(f"🚀 Starting notebook fixing process for: {notebook_path}")

        # Create tasks and crew with the specific notebook path
        self._create_tasks(notebook_path)
        self._create_crew()

        results = {
            "notebook_path": notebook_path,
            "success": False,
            "iterations": 0,
            "logs": [],
            "final_status": "",
        }

        for iteration in range(max_iterations):
            results["iterations"] = iteration + 1
            print(f"\n🔄 Iteration {iteration + 1}/{max_iterations}")

            try:
                # Create a backup of the notebook
                backup_path = f"{notebook_path}.backup.{iteration}"
                subprocess.run(["cp", notebook_path, backup_path])

                # Run the crew to analyze and fix
                crew_result = self.crew.kickoff()

                results["logs"].append(
                    {
                        "iteration": iteration + 1,
                        "timestamp": datetime.now().isoformat(),
                        "result": str(crew_result),
                    }
                )

                # Check validation result from our tool instead of external jupyter
                execution_tool = NotebookExecutionTool()
                validation_result = execution_tool._run(notebook_path=notebook_path)

                if "✅ SUCCESS" in validation_result:
                    print(
                        f"✅ Notebook fixed successfully in iteration {iteration + 1}"
                    )
                    results["success"] = True
                    results["final_status"] = "Successfully fixed and validated"
                    break
                elif "❌ EXECUTION FAILED" in validation_result:
                    print(f"🔄 Error found in iteration {iteration + 1}, continuing...")
                    results["logs"][-1]["execution_error"] = validation_result
                    # Continue to next iteration to fix the newly discovered error
                else:
                    print(f"❌ Iteration {iteration + 1} had unexpected result...")
                    results["logs"][-1]["execution_error"] = validation_result

            except Exception as e:
                error_msg = f"❌ Error in iteration {iteration + 1}: {str(e)}"
                print(error_msg)
                results["logs"].append(
                    {
                        "iteration": iteration + 1,
                        "error": error_msg,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

        if not results["success"]:
            results["final_status"] = f"Failed to fix after {max_iterations} iterations"

        # Save results to file
        results_path = f"{notebook_path}.fix_results.json"
        with open(results_path, "w") as f:
            json.dump(results, f, indent=2)

        print(f"\n📊 Results saved to: {results_path}")
        return results


def main():
    """Main function to demonstrate the notebook fixing system."""
    if not CREWAI_AVAILABLE or not RAG_AVAILABLE:
        print("❌ Missing dependencies. Please install:")
        print("uv add crewai langchain-ollama langchain-chroma chromadb")
        return

    # Initialize the notebook fixer crew
    fixer = NotebookFixerCrew()

    # Fix the specified notebook
    notebook_path = "/Users/aya/Desktop/atoti/02-technical-guides/multidimensional-analysis/main.ipynb"

    print(f"🎯 Fixing notebook: {notebook_path}")
    results = fixer.fix_notebook(notebook_path, max_iterations=3)

    # Print summary
    print("\n" + "=" * 60)
    print("📋 FIXING SUMMARY")
    print("=" * 60)
    print(f"Notebook: {results['notebook_path']}")
    print(f"Success: {results['success']}")
    print(f"Iterations: {results['iterations']}")
    print(f"Status: {results['final_status']}")

    if results["success"]:
        print("\n🎉 Notebook has been successfully fixed!")
    else:
        print("\n😞 Notebook fixing failed. Check the logs for details.")

    return results


if __name__ == "__main__":
    main()
