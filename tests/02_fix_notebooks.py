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


class NotebookEditTool(BaseTool):
    """Tool for editing notebook cells."""

    name: str = "notebook_edit"
    description: str = (
        "Edit a specific cell in a Jupyter notebook. Requires notebook_path (full file path), "
        "cell_id (the unique cell identifier), and new_content (the new code for the cell). "
        "Use cell_id to specify which cell to edit."
    )

    def _run(self, notebook_path: str, cell_id: str, new_content: str) -> str:
        """Edit a notebook cell with new content."""
        try:
            import json

            with open(notebook_path, "r", encoding="utf-8") as f:
                notebook_data = json.load(f)

            # Find the target cell by ID
            target_cell = None
            for cell in notebook_data.get("cells", []):
                if cell.get("id") == cell_id:
                    target_cell = cell
                    break

            if target_cell is None:
                return f"❌ Cell with ID '{cell_id}' not found in notebook."

            if target_cell.get("cell_type") != "code":
                return f"❌ Cell with ID '{cell_id}' is not a code cell (type: {target_cell.get('cell_type')})."

            # Update the cell content
            # Jupyter notebooks store source as a list of strings
            if isinstance(new_content, str):
                # Split into lines and add newlines except for the last line
                lines = new_content.split("\n")
                source_lines = []
                for i, line in enumerate(lines):
                    if i < len(lines) - 1:  # Not the last line
                        source_lines.append(line + "\n")
                    else:  # Last line
                        source_lines.append(line)
                target_cell["source"] = source_lines
            else:
                target_cell["source"] = [new_content]

            # Clear any previous outputs
            target_cell["outputs"] = []
            target_cell["execution_count"] = None

            # Save the notebook back
            with open(notebook_path, "w", encoding="utf-8") as f:
                json.dump(notebook_data, f, indent=1, ensure_ascii=False)

            return f"✅ Successfully edited code cell with ID '{cell_id}'"

        except Exception as e:
            return f"❌ Edit failed: {str(e)}"


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
        "Search the atoti documentation using RAG to find relevant information."
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

    def _run(self, query: str, k: int = 5) -> str:
        """Search the vectordb for relevant documentation."""
        if not self._vectordb:
            return "❌ RAG system not initialized"

        try:
            docs = self._vectordb.similarity_search(query, k=k)
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
        edit_tool = NotebookEditTool()
        rag_tool = RAGSearchTool(self.vectordb_path)
        file_read_tool = FileReadTool()

        self.analyzer_agent = Agent(
            role="Notebook Error Analyzer",
            goal="Analyze notebook execution errors and identify root causes",
            backstory="""You are an expert Python developer specializing in Jupyter notebooks and atoti.
            You can analyze execution errors, understand stack traces, and identify the specific issues
            that need to be fixed. You use RAG to search documentation for solutions.
            
            IMPORTANT: You focus ONLY on notebook files and atoti documentation. You do NOT read
            atoti source code files, library internals, or other Python modules. Your expertise
            is in understanding notebook execution and finding solutions in the atoti documentation.""",
            tools=[execution_tool, rag_tool, file_read_tool],
            llm=self.llm,
            verbose=True,
            allow_delegation=False,
        )

        self.fixer_agent = Agent(
            role="Code Fixer",
            goal="Execute the fix recommended by the analyzer by editing the correct cell and confirming the save",
            backstory="""You are a precise code editor focused on implementing fixes that have already been analyzed.
            Your job is straightforward execution:
            - Take the fix recommendations from the analyzer
            - Implement the recommended fix using notebook_edit tool
            - Verify the notebook was properly saved by reading it back
            
            You don't need to research or analyze - the analyzer has already determined what needs to be fixed.
            Your expertise is in precise execution and ensuring edits are applied correctly.
            
            IMPORTANT: You work ONLY with notebook files. You do NOT read atoti source code files, 
            library internals, or other Python modules.
            
            AVAILABLE TOOLS:
            - notebook_edit: Edit a specific cell in a Jupyter notebook using cell_id
            - file_read: Read the contents of files to verify changes
            
            You MUST use these tools to complete your tasks. Do not provide manual instructions.""",
            tools=[edit_tool, file_read_tool],
            llm=self.llm,
            verbose=True,
            allow_delegation=False,
        )

        self.validator_agent = Agent(
            role="Solution Validator",
            goal="Test fixes and ensure they work correctly",
            backstory="""You are a QA engineer who validates that fixes actually resolve the issues.
            You run tests, check outputs, and ensure the notebook executes successfully from start
            to finish without errors.
            
            IMPORTANT: You focus ONLY on notebook execution and validation. You do NOT read
            atoti source code files, library internals, or other Python modules. Your role is
            to validate notebook execution and identify any remaining errors.""",
            tools=[execution_tool, file_read_tool],
            llm=self.llm,
            verbose=True,
            allow_delegation=False,
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
            
            YOUR ROLE: You are an ANALYZER ONLY. You do NOT edit files. You only analyze and recommend.
            
            STEP 1 - EXECUTE: Execute the notebook using notebook_execution tool with notebook_path: {notebook_path}
            STEP 2 - READ NOTEBOOK: Read the notebook file using file_read tool with file_path: {notebook_path}
            STEP 3 - SEARCH DOCS: Use RAG search tool to find relevant atoti documentation for any errors found
            STEP 4 - PROVIDE RECOMMENDATION: Output your analysis in the required format below
            
            CRITICAL PATH RESTRICTIONS:
            - ALWAYS use the exact path provided: {notebook_path}
            - Do NOT construct your own paths or use relative paths
            - Do NOT read any files other than: {notebook_path}
            - Do NOT attempt to edit any files - you are an analyzer only
            
            OUTPUT REQUIREMENTS - Provide EXACTLY this format:
            CELL_ID: [cell_id] (the exact cell ID from the notebook)
            FIXED_CODE: 
            ```python
            [exact corrected code for the cell]
            ```
            
            ANALYSIS PROCESS:
            - Focus on the FIRST ERROR found - this is usually the root cause that triggers cascading failures
            - Identify which code cell contains the error by its unique cell ID
            - Based on atoti documentation, write the corrected version of that cell's code
            - Provide the complete corrected cell content, not just the changed line
            
            When reading the notebook file, look for code cells and their IDs like:
            "cell_type": "code",
            "id": "abc12345-1234-1234-1234-123456789abc"
            
            Use the exact cell ID in your output.
            
            IMPORTANT REMINDERS:
            - You ANALYZE and RECOMMEND only
            - The CodeFixer will implement your recommendation
            - Use ONLY the provided path: {notebook_path}
            - Output must include CELL_ID and FIXED_CODE in the exact format above
            """,
            agent=self.analyzer_agent,
            expected_output="CELL_ID and FIXED_CODE in the specified format for direct implementation",
        )

        self.fixing_task = Task(
            description=f"""Execute the fix provided by the analyzer.

            NOTEBOOK PATH: {notebook_path}
            
            STEP 1 - PARSE ANALYZER OUTPUT: Extract the CELL_ID and FIXED_CODE from the analyzer's output
            STEP 2 - IMPLEMENT FIX: Use notebook_edit tool with notebook_path: {notebook_path}, cell_id and new_content from analyzer
            STEP 3 - VERIFY SAVE: Use file_read tool with file_path: {notebook_path} to confirm the notebook was properly saved
            
            IMPORTANT FILE RESTRICTIONS:
            - ONLY read the target notebook file: {notebook_path}
            - Do NOT read atoti source files, library code, or other Python modules
            - Focus purely on executing the exact fix provided by the analyzer
            
            EXECUTION PRINCIPLES:
            - Look for "CELL_ID: [cell_id]" in the analyzer output
            - Look for "FIXED_CODE:" followed by a python code block in the analyzer output
            - Use notebook_edit with the exact cell_id and code content provided
            - Confirm the file was saved correctly by reading it back
            
            EXAMPLE WORKFLOW:
            1. Parse analyzer output to get:
               cell_id="[the-actual-cell-id-from-analyzer]" 
               new_content="import pandas as pd\\nimport atoti as tt\\n\\nsession = tt.Session.connect()"
            2. notebook_edit(notebook_path="{notebook_path}", 
               cell_id="[the-actual-cell-id-from-analyzer]", 
               new_content="[exact code from analyzer]")
            3. file_read(file_path="{notebook_path}") → Verify the change was saved
            
            CRITICAL: 
            - Use ONLY the notebook path: {notebook_path}
            - Execute the exact fix from analyzer and confirm the notebook was saved correctly.
            """,
            agent=self.fixer_agent,
            expected_output="Fix implemented exactly as provided by analyzer and notebook save confirmed",
        )

        self.validation_task = Task(
            description=f"""Validate the fix and check for any remaining errors.

            NOTEBOOK PATH: {notebook_path}
            
            STEP 1 - EXECUTE: Run the notebook using notebook_execution tool with notebook_path: {notebook_path}
            STEP 2 - READ NOTEBOOK: Read the notebook file using file_read tool with file_path: {notebook_path} to verify current state
            STEP 3 - ANALYZE RESULTS: 
                - If NO errors: Report complete success
                - If NEW errors appear: Provide detailed analysis of the NEXT error found
                - Report any remaining issues that need another iteration
            
            IMPORTANT FILE RESTRICTIONS:
            - ONLY read the target notebook file: {notebook_path}
            - Do NOT read atoti source files, library code, or other Python modules
            - Focus on notebook validation and execution results only
            
            CRITICAL ERROR CASCADE DETECTION:
            After fixing the first error, NEW errors may become visible that were hidden before.
            If you find any remaining errors, provide:
            - Exact error message and location of the NEXT error
            - Whether this is a new error revealed after the fix
            - Detailed analysis for the next iteration
            
            CRITICAL: 
            - Use ONLY the notebook path: {notebook_path}
            - Either confirm complete success OR identify the next error for iteration.
            """,
            agent=self.validator_agent,
            expected_output="Complete success confirmation OR detailed next error analysis for iteration",
        )

        print("✅ Tasks created")

    def _create_crew(self):
        """Create the CrewAI crew with sequential process."""
        self.crew = Crew(
            agents=[self.analyzer_agent, self.fixer_agent, self.validator_agent],
            tasks=[self.analysis_task, self.fixing_task, self.validation_task],
            process=Process.sequential,
            verbose=True,
        )
        print("✅ Crew created")

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
