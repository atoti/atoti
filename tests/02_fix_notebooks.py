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

# CrewAI imports
from crewai import Agent, Task, Crew, Process
from crewai.tools import BaseTool

# RAG and Vector DB imports
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_chroma import Chroma

# Configuration constants
NOTEBOOK_EXECUTION_TIMEOUT = 120  # seconds
NOTEBOOK_EXECUTION_CELL_TIMEOUT = 60  # seconds
MAX_ERROR_CONTEXT_LINES = 40
MAX_RAW_ERROR_LINES = 30
MAX_FILE_CONTENT_PREVIEW = 2000  # characters


class NotebookExecutionTool(BaseTool):
    """Tool for executing notebook cells and capturing output."""

    name: str = "notebook_execution"
    description: str = (
        "Execute a Jupyter notebook and return the output or error. "
        "Use notebook_path parameter (not JSON) with the complete file path to the .ipynb file. "
        "Example: notebook_path='/Users/aya/Desktop/atoti/notebook.ipynb' "
        "This will execute the entire notebook."
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

            # Try to extract more specific error information
            if hasattr(e, "output") and e.output:
                error_msg = e.output
            elif hasattr(e, "traceback") and e.traceback:
                error_msg = e.traceback

            return f"❌ EXECUTION ERROR: {error_msg}"


class NotebookAnalysisTool(BaseTool):
    """Tool for analyzing notebook execution errors and extracting error details."""

    name: str = "notebook_analysis"
    description: str = (
        "Analyze execution errors from a Jupyter notebook and extract detailed error information. "
        "Takes execution_error_output (from notebook_execution tool) and provides structured error details "
        "without specifying cell locations."
    )

    def _run(self, execution_error_output: str = None) -> str:
        """Analyze execution errors and extract detailed error information."""
        try:
            # If no execution error provided or success reported
            if not execution_error_output or "✅ SUCCESS" in execution_error_output:
                return "📋 No errors detected in notebook execution"

            # Parse execution error to extract key information
            error_analysis = self._parse_execution_error(execution_error_output)

            # Compile detailed error analysis report
            result = "🔍 NOTEBOOK ERROR ANALYSIS\n"
            result += "=" * 40 + "\n\n"

            # Error summary
            result += f"🐛 ERROR TYPE: {error_analysis['error_type']}\n"
            result += f"💬 ERROR MESSAGE: {error_analysis['error_message']}\n\n"

            # Failing cell code (if captured)
            if error_analysis["cell_content"]:
                result += "📝 FAILING CODE:\n"
                result += "```python\n"
                result += error_analysis["cell_content"]
                result += "\n```\n\n"

            # Full traceback for context
            if error_analysis["full_traceback"]:
                result += "📋 FULL TRACEBACK:\n"
                for line in error_analysis["full_traceback"][:20]:  # Limit output
                    result += f"{line}\n"
                if len(error_analysis["full_traceback"]) > 20:
                    result += "... (truncated)\n"

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


class NotebookEditTool(BaseTool):
    """Intelligent tool for editing notebook cells based on analysis recommendations."""

    name: str = "notebook_edit"
    description: str = (
        "Intelligently edit notebook cells based on analysis recommendations. "
        "This tool analyzes the recommendations, determines which cells need fixing, "
        "identifies the appropriate changes, and applies them automatically. "
        "Requires notebook_path and analysis_output from the analyzer agent."
    )

    def _run(self, notebook_path: str, analysis_output: str) -> str:
        """Intelligently analyze recommendations and apply fixes to the notebook."""
        try:
            import nbformat

            # Read the notebook
            with open(notebook_path, "r", encoding="utf-8") as f:
                notebook = nbformat.read(f, as_version=4)

            # Find code cells only
            code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]

            if not code_cells:
                return "❌ No code cells found in the notebook."

            # Extract fix information from analysis - try structured format first
            before_code = self._extract_before_code(analysis_output)
            after_code = self._extract_after_code(analysis_output)

            # If we have structured before/after code, use that
            if before_code and after_code:
                target_cell_index = self._find_matching_cell(before_code, code_cells)
                if target_cell_index is not None:
                    return self._apply_fix(
                        notebook,
                        code_cells,
                        target_cell_index,
                        after_code,
                        notebook_path,
                    )

            # If no structured format found, return error - analyzer must provide proper format
            return "❌ Analysis output missing required BEFORE_CODE/AFTER_CODE format. Analyzer must provide structured output with BEFORE_CODE: and AFTER_CODE: sections."

        except Exception as e:
            return f"❌ Edit failed: {str(e)}"

    def _extract_before_code(self, analysis_output: str) -> str:
        """Extract BEFORE_CODE from structured analysis output."""
        import re

        pattern = r"BEFORE_CODE:\s*```python\s*(.*?)\s*```"
        match = re.search(pattern, analysis_output, re.DOTALL)
        return match.group(1).strip() if match else None

    def _extract_after_code(self, analysis_output: str) -> str:
        """Extract AFTER_CODE from structured analysis output."""
        import re

        pattern = r"AFTER_CODE:\s*```python\s*(.*?)\s*```"
        match = re.search(pattern, analysis_output, re.DOTALL)
        return match.group(1).strip() if match else None

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
                model="ollama/devstral:latest",  # Use ollama/ prefix for CrewAI/LiteLLM compatibility
                temperature=0.1,
                base_url="http://localhost:11434",
            )
            print("✅ Devstral model initialized")
        except Exception as e:
            print(f"❌ Failed to initialize Devstral model: {e}")
            self.llm = None

    def _initialize_tools(self):
        """Initialize all tools for the agents."""
        # Create single instances to be shared across agents
        self.execution_tool = NotebookExecutionTool()
        self.analysis_tool = NotebookAnalysisTool()
        self.edit_tool = NotebookEditTool()
        self.rag_tool = RAGSearchTool(self.vectordb_path)
        self.file_read_tool = FileReadTool()
        self.directory_read_tool = DirectoryReadTool()

        print("✅ Tools initialized")

    def _create_agents(self):
        """Create two specialized agents for the notebook fixing workflow."""

        self.analyzer_agent = Agent(
            role="Jupyter Notebook Error Diagnostician specializing in atoti library troubleshooting",
            goal="Deliver complete, implementable fix recommendations by conducting comprehensive RAG searches that produce ready-to-use before/after code snippets based on official atoti documentation examples",
            backstory="""You are a senior Python developer with 15+ years of experience debugging Jupyter notebooks and specialized expertise in the atoti analytics library. You've diagnosed thousands of notebook failures across data science teams and have developed a systematic approach to error analysis.

Your methodology is renowned for being both thorough and definitive:
- You execute notebooks exactly once to capture pristine error states
- You conduct comprehensive RAG searches that find COMPLETE working code examples
- You extract full code patterns from documentation, not just concepts
- You provide complete, ready-to-implement before/after code blocks

Your RAG search expertise is legendary among teams:
- You know how to query atoti documentation with specific error messages and function names
- You excel at finding complete code examples that show the exact syntax transformations needed
- You always extract FULL code blocks from documentation, ensuring implementers have everything they need
- You provide complete context in your code snippets, including necessary imports and setup

Your colleagues know you for your discipline in workflow execution - you never re-run analyses after completing your research phase, as you've learned that multiple executions can mask important error patterns. Your RAG searches are so comprehensive that by the time you complete them, you have complete, working solutions ready for immediate implementation.

You pride yourself on delivering complete before/after code comparisons that require no additional research or guesswork from implementation teams.

CRITICAL: You ALWAYS follow the exact output format specification. You understand that the downstream editing tool depends on finding "BEFORE_CODE:" and "AFTER_CODE:" markers with ```python``` code blocks. You never deviate from this format because you know that any deviation will cause the entire fixing pipeline to fail. If you cannot provide proper BEFORE_CODE/AFTER_CODE blocks, you report NO_ERRORS instead of providing incomplete output.""",
            tools=[self.execution_tool, self.rag_tool],
            llm=self.llm,
            verbose=True,
            allow_delegation=False,
        )

        self.editor_agent = Agent(
            role="Notebook Code Implementation Specialist with expertise in cell-level editing",
            goal="Apply code fixes with precision and validate results through comprehensive testing, ensuring that every edit resolves the specific issue while maintaining notebook integrity and functionality",
            backstory="""You are a meticulous code editor with 10+ years of experience implementing fixes in production Jupyter notebooks. You've become known for your ability to translate analysis recommendations into flawless code implementations.

Your approach is systematic and careful:
- You excel at analyzing notebook structure and determining which cells need modification
- You can understand error analysis and translate recommendations into precise code fixes
- You make intelligent decisions about what changes are needed based on the analysis context
- You always validate changes through execution testing to ensure fixes work as intended
- You believe in the principle of "understand the problem, implement the solution, then verify thoroughly"

Your track record shows consistently successful fix implementations because you:
1. Analyze the full context before making any changes
2. Determine the exact cell and content modifications needed
3. Apply changes systematically and validate through testing
4. Provide clear success/failure reporting with detailed error context when issues persist

Teams rely on you because you implement fixes intelligently without requiring overly specific instructions, and your validation process catches any edge cases that might need additional iteration.""",
            tools=[self.edit_tool, self.execution_tool],
            llm=self.llm,
            verbose=True,
            allow_delegation=False,
        )

        print("✅ Agents created")

        # Debug: Print tool information
        print(
            f"🔧 Analyzer agent tools: {[tool.name for tool in self.analyzer_agent.tools]}"
        )
        print(
            f"🔧 Editor agent tools: {[tool.name for tool in self.editor_agent.tools]}"
        )

    def _create_tasks(self, notebook_path: str):
        """Create two specialized tasks for the notebook fixing workflow."""

        self.analysis_task = Task(
            description=f"""CONTEXT: You are analyzing a Jupyter notebook to identify execution errors and provide complete, ready-to-implement fix recommendations. Your RAG searches must produce comprehensive solutions that result in final before/after code snippets.

NOTEBOOK PATH: {notebook_path}

EXECUTION PROTOCOL (CRITICAL - FOLLOW EXACTLY):
STEP 1: Execute the notebook ONCE using notebook_execution tool with notebook_path parameter set to: {notebook_path}
STEP 2: IF execution succeeds → Report ANALYSIS_STATUS: NO_ERRORS and STOP immediately
STEP 3: IF execution fails → Extract complete error details (error type, message, full failing code)
STEP 4: Perform targeted RAG search #1: Search using specific error message + function names to find complete solution patterns
STEP 5: OPTIONAL: Perform RAG search #2 only if first search doesn't provide complete before/after code examples
STEP 6: Synthesize RAG findings into complete, implementable before/after code snippets
STEP 7: STOP - Never execute the notebook again after RAG searches

CRITICAL: When using notebook_execution tool, use notebook_path="{notebook_path}" (without any JSON formatting)

RAG SEARCH STRATEGY (CRITICAL FOR SUCCESS):
- RAG Search #1: Use exact error message + failing function names (e.g., "AttributeError session.create_cube" or "ImportError atoti")
- RAG Search #2 (if needed): Use broader context terms (e.g., "atoti cube creation syntax" or "session setup examples")
- Extract COMPLETE code patterns from RAG results, not just concepts
- Look for full before/after examples in the documentation
- Identify exact syntax changes needed for atoti API migrations

ANALYSIS METHODOLOGY:
- Focus on the FIRST error encountered (single issue resolution)
- Extract the COMPLETE failing code block from execution output
- Use RAG documentation to find COMPLETE working code examples
- Provide FULL before/after code blocks, not partial snippets
- Ensure the after code is a complete, runnable replacement

ERROR HANDLING RULES:
- Always use the exact notebook path provided: {notebook_path}
- Never modify or guess notebook paths
- Base recommendations on: initial execution error + COMPLETE RAG examples
- Never re-execute after completing RAG searches

REQUIRED OUTPUT FORMAT (CRITICAL - FOLLOW EXACTLY):
ANALYSIS_STATUS: [COMPLETE | NO_ERRORS]

IF ANALYSIS_STATUS: NO_ERRORS
- RESULT: Notebook executes successfully without errors

IF ANALYSIS_STATUS: COMPLETE
- ERROR_DESCRIPTION: [Specific error and root cause]
- MINIMAL_CHANGE: [Describe the exact change needed]
- BEFORE_CODE:
```python
[COMPLETE failing code block from execution error - include full context]
```
- AFTER_CODE:
```python
[COMPLETE corrected code block based on RAG examples - ready to run]
```
- CONFIDENCE: [HIGH | MEDIUM | LOW]
- REASONING: [Explanation based on specific atoti documentation examples found in RAG]
- RAG_SEARCHES_USED: [1 | 2]

CRITICAL FORMAT ENFORCEMENT:
- You MUST output exactly the format above
- The editing tool depends on finding "BEFORE_CODE:" and "AFTER_CODE:" markers
- Both code blocks must be wrapped in ```python``` fences
- Do not deviate from this format - any deviation will cause tool failure
- If you cannot provide BEFORE_CODE and AFTER_CODE, report ANALYSIS_STATUS: NO_ERRORS instead

FORMAT VALIDATION CHECKLIST:
□ Does output contain "ANALYSIS_STATUS: COMPLETE" or "ANALYSIS_STATUS: NO_ERRORS"?
□ If COMPLETE, does it contain "BEFORE_CODE:" followed by ```python```?
□ If COMPLETE, does it contain "AFTER_CODE:" followed by ```python```?
□ Are both code blocks complete and runnable?
□ Is the format exactly as specified above?

SUCCESS CRITERIA:
- Single execution with exact path usage
- RAG searches that find COMPLETE working code examples
- FULL before/after code blocks that are ready for direct implementation
- After code includes all necessary imports, context, and complete syntax
- Clear reasoning based on specific documentation examples found""",
            agent=self.analyzer_agent,
            expected_output="Efficient analysis with minimal fix determination and before/after code comparison",
        )

        self.editing_task = Task(
            description=f"""CONTEXT: You are implementing a code fix based on analyzer recommendations. Your role is to intelligently apply the appropriate fix using the intelligent notebook editing tool.

NOTEBOOK PATH: {notebook_path}

INPUT REQUIREMENTS:
- Analysis output from the analyzer agent containing error details and recommendations
- The notebook editing tool will handle structure analysis and fix determination
- You need to validate the fix by executing the notebook

IMPLEMENTATION WORKFLOW:
STEP 1: Validate that analysis output contains required BEFORE_CODE: and AFTER_CODE: sections
STEP 2: Use the notebook_edit tool with the analysis output to automatically:
    - Analyze the notebook structure 
    - Determine the appropriate fix based on the analysis
    - Locate the correct cell(s) to edit
    - Apply the necessary changes
STEP 3: Execute the complete notebook to validate the fix
STEP 4: Report results based on execution outcome

FORMAT VALIDATION:
- First check if analysis contains "BEFORE_CODE:" and "AFTER_CODE:" markers
- If format is invalid, report FAILED with specific format error details
- Only proceed with editing if proper format is confirmed

VALIDATION REQUIREMENTS:
- Always execute the full notebook after the edit tool completes
- Report SUCCESS only if notebook executes completely without errors
- Report NEEDS_ITERATION if fix applied but other errors remain
- Report FAILED if the edit tool was unable to determine or apply appropriate fix

REQUIRED OUTPUT FORMAT:
EDIT_STATUS: [SUCCESS | FAILED | NEEDS_ITERATION]

IF EDIT_STATUS: SUCCESS
- RESULT: Fix applied successfully, notebook executes without errors
- DETAILS: [What changes were made and validation results]

IF EDIT_STATUS: FAILED  
- ERROR: [Specific implementation error encountered]
- DETAILS: [What the edit tool reported and why it failed]

IF EDIT_STATUS: NEEDS_ITERATION
- RESULT: Fix applied but notebook still has errors  
- REMAINING_ERROR: [Description of new/remaining error for next iteration]
- DETAILS: [Changes made and current error state]

SUCCESS CRITERIA:
- Successful use of the intelligent notebook editing tool
- Complete notebook execution without errors after fix application
- Clear reporting of success/failure status for iteration control""",
            agent=self.editor_agent,
            expected_output="Intelligent fix implementation and validation results with clear status",
            context=[self.analysis_task],
        )

        print("✅ Tasks created")

    def _create_crew(self):
        """Create the CrewAI crew with two specialized agents."""
        self.crew = Crew(
            agents=[self.analyzer_agent, self.editor_agent],
            tasks=[self.analysis_task, self.editing_task],
            process=Process.sequential,
            verbose=True,
        )
        print("✅ Crew created with two specialized agents")

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

                # Run the two-agent workflow to analyze and fix
                crew_result = self.crew.kickoff()

                results["logs"].append(
                    {
                        "iteration": iteration + 1,
                        "timestamp": datetime.now().isoformat(),
                        "result": str(crew_result),
                    }
                )

                # Check the editor's status decision
                crew_output = str(crew_result)

                if "EDIT_STATUS: SUCCESS" in crew_output:
                    print(
                        f"✅ Notebook fixed successfully in iteration {iteration + 1}"
                    )
                    results["success"] = True
                    results["final_status"] = (
                        "Successfully fixed and validated by editor"
                    )
                    break
                elif "ANALYSIS_STATUS: NO_ERRORS" in crew_output:
                    print(f"✅ Notebook already working in iteration {iteration + 1}")
                    results["success"] = True
                    results["final_status"] = "No errors found by analyzer"
                    break
                elif "EDIT_STATUS: NEEDS_ITERATION" in crew_output:
                    print(
                        f"🔄 Editor reports more work needed, continuing to iteration {iteration + 2}"
                    )
                    # Continue to next iteration
                elif "EDIT_STATUS: FAILED" in crew_output:
                    print(f"❌ Editor failed to apply fix in iteration {iteration + 1}")
                    # Continue to next iteration to try again
                else:
                    # Fallback: Check execution independently if status unclear
                    execution_tool = NotebookExecutionTool()
                    validation_result = execution_tool._run(notebook_path=notebook_path)

                    if "✅ SUCCESS" in validation_result:
                        print(
                            f"✅ Notebook fixed successfully in iteration {iteration + 1}"
                        )
                        results["success"] = True
                        results["final_status"] = "Successfully fixed and validated"
                        break
                    else:
                        print(
                            f"🔄 Error found in iteration {iteration + 1}, continuing..."
                        )
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
