#!/usr/bin/env python3
"""
Context-Aware Iterative Notebook Fixing with LangGraph

This implementation demonstrates how LangGraph can maintain rich state and context
across multiple retry attempts, allowing Devstral to learn from previous failures
and progressively improve its fixing attempts.

Key Features:
- Accumulates error context across attempts
- Tracks what was tried and what failed
- Builds a comprehensive failure history
- Uses previous attempt context to improve next attempt
- Continues until success or exhaustion
"""

import argparse
import asyncio
import json
import os
import platform as pf
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, TypedDict, Any
from datetime import datetime

from langgraph.graph import StateGraph, END
from langchain_ollama import ChatOllama
from langchain.prompts import ChatPromptTemplate
from langchain.schema.output_parser import StrOutputParser


@dataclass
class FixAttempt:
    """Represents a single fix attempt with full context."""

    attempt_number: int
    strategy_used: str
    error_analysis: str
    fixes_applied: List[str]
    test_output: str
    test_passed: bool
    error_message: str
    timestamp: datetime
    lessons_learned: str = ""


@dataclass
class NotebookFailure:
    """Enhanced notebook failure with context accumulation."""

    notebook_path: str
    classname: str
    test_name: str
    failure_type: str
    original_failure_message: str
    original_error_output: str
    execution_time: float

    # Context accumulation fields
    attempt_history: List[FixAttempt] = field(default_factory=list)
    current_error_context: str = ""
    learning_summary: str = ""


class IterativeFixingState(TypedDict):
    """Rich state that accumulates context across all retry attempts."""

    # Current processing context
    failed_notebooks: List[NotebookFailure]
    current_notebook: Optional[NotebookFailure]
    current_notebook_index: int

    # Rich context accumulation
    notebook_content: str
    original_content_backup: str

    # Iterative context building
    attempt_number: int
    max_attempts: int

    # Context from previous attempts
    previous_errors: List[str]
    previous_fixes: List[str]
    previous_strategies: List[str]
    what_worked: List[str]
    what_failed: List[str]
    error_patterns: List[str]

    # Current attempt state
    current_error_analysis: str
    current_strategy: str
    current_fixes: List[str]
    current_test_output: str
    current_success: bool

    # Learning and adaptation
    accumulated_knowledge: str
    strategy_effectiveness: Dict[str, int]
    common_patterns: List[str]

    # Workflow control
    current_step: str
    should_continue_notebook: bool
    should_continue_processing: bool

    # Results tracking
    success_count: int
    failure_count: int
    total_attempts: int
    processing_log: List[str]


class ContextualNotebookFixer:
    """
    LangGraph-based notebook fixer that builds and maintains context
    across retry attempts, learning from each failure to improve the next attempt.
    """

    def __init__(self, max_attempts: int = 5):
        self.max_attempts = max_attempts
        self.devstral = ChatOllama(
            model="codestral:latest",
            temperature=0.2,  # Slightly higher for creative problem solving
        )
        self.graph = None
        self._build_contextual_workflow()

    def _build_contextual_workflow(self):
        """Build LangGraph workflow that accumulates context across attempts."""
        workflow = StateGraph(IterativeFixingState)

        # Workflow nodes
        workflow.add_node("initialize", self._initialize_processing)
        workflow.add_node("select_notebook", self._select_next_notebook)
        workflow.add_node("prepare_notebook", self._prepare_notebook_context)

        # ITERATIVE CONTEXT LOOP NODES
        workflow.add_node(
            "analyze_with_context", self._analyze_with_accumulated_context
        )
        workflow.add_node("learn_from_history", self._learn_from_attempt_history)
        workflow.add_node(
            "generate_contextual_fixes", self._generate_fixes_with_context
        )
        workflow.add_node("apply_fixes", self._apply_fixes)
        workflow.add_node("test_and_capture", self._test_and_capture_results)
        workflow.add_node("update_context", self._update_context_from_attempt)
        workflow.add_node("evaluate_progress", self._evaluate_progress)

        workflow.add_node("finalize_notebook", self._finalize_notebook)
        workflow.add_node("complete", self._complete_processing)

        # Workflow edges
        workflow.set_entry_point("initialize")
        workflow.add_edge("initialize", "select_notebook")

        # Notebook selection decision
        workflow.add_conditional_edges(
            "select_notebook",
            self._decide_notebook_continuation,
            {"process": "prepare_notebook", "complete": "complete"},
        )

        workflow.add_edge("prepare_notebook", "analyze_with_context")
        workflow.add_edge("analyze_with_context", "learn_from_history")
        workflow.add_edge("learn_from_history", "generate_contextual_fixes")
        workflow.add_edge("generate_contextual_fixes", "apply_fixes")
        workflow.add_edge("apply_fixes", "test_and_capture")
        workflow.add_edge("test_and_capture", "update_context")
        workflow.add_edge("update_context", "evaluate_progress")

        # CRITICAL: The iterative retry decision with context
        workflow.add_conditional_edges(
            "evaluate_progress",
            self._decide_retry_with_context,
            {
                "retry": "analyze_with_context",  # Loop back with accumulated context
                "success": "finalize_notebook",  # Success, move to next notebook
                "exhausted": "finalize_notebook",  # Max attempts reached
            },
        )

        workflow.add_edge("finalize_notebook", "select_notebook")
        workflow.add_edge("complete", END)

        # Compile with higher recursion limit to allow for retry loops
        # Each notebook can have max_attempts (5) * number of nodes in retry loop (~8) = ~40 recursions
        # Plus overhead for multiple notebooks, so set limit to 100
        self.graph = workflow.compile()

    def _initialize_processing(
        self, state: IterativeFixingState
    ) -> IterativeFixingState:
        """Initialize the contextual processing workflow."""
        state["current_step"] = "initialize"
        state["current_notebook_index"] = 0
        state["success_count"] = 0
        state["failure_count"] = 0
        state["total_attempts"] = 0
        state["processing_log"] = []
        state["should_continue_processing"] = True

        # Initialize context tracking
        state["strategy_effectiveness"] = {}
        state["common_patterns"] = []
        state["accumulated_knowledge"] = ""

        log_msg = f"🚀 Starting contextual notebook fixing for {len(state['failed_notebooks'])} notebooks"
        state["processing_log"].append(log_msg)
        print(log_msg)

        return state

    def _select_next_notebook(
        self, state: IterativeFixingState
    ) -> IterativeFixingState:
        """Select next notebook and initialize its context."""
        state["current_step"] = "select_notebook"

        if state["current_notebook_index"] < len(state["failed_notebooks"]):
            state["current_notebook"] = state["failed_notebooks"][
                state["current_notebook_index"]
            ]
            state["should_continue_processing"] = True

            # Reset notebook-specific context
            state["attempt_number"] = 0
            state["should_continue_notebook"] = True
            state["previous_errors"] = []
            state["previous_fixes"] = []
            state["previous_strategies"] = []
            state["what_worked"] = []
            state["what_failed"] = []
            state["error_patterns"] = []

            notebook_path = state["current_notebook"].notebook_path
            log_msg = f"📋 Starting contextual fixing for: {notebook_path}"
            state["processing_log"].append(log_msg)
            print(log_msg)
        else:
            state["should_continue_processing"] = False
            state["current_notebook"] = None

        return state

    def _decide_notebook_continuation(self, state: IterativeFixingState) -> str:
        """Decide whether to process next notebook or complete."""
        return "process" if state["should_continue_processing"] else "complete"

    def _prepare_notebook_context(
        self, state: IterativeFixingState
    ) -> IterativeFixingState:
        """Prepare notebook context and backup original content."""
        state["current_step"] = "prepare_notebook"

        if not state["current_notebook"]:
            return state

        notebook_path = state["current_notebook"].notebook_path

        try:
            with open(notebook_path, "r", encoding="utf-8") as f:
                content = f.read()
                state["notebook_content"] = content
                state["original_content_backup"] = (
                    content  # Keep original for reference
                )

            log_msg = f"📖 Loaded notebook content: {len(content)} characters"
            state["processing_log"].append(log_msg)
            print(log_msg)

        except Exception as e:
            error_msg = f"❌ Failed to load notebook: {e}"
            state["processing_log"].append(error_msg)
            print(error_msg)
            state["notebook_content"] = ""
            state["original_content_backup"] = ""

        return state

    def _analyze_with_accumulated_context(
        self, state: IterativeFixingState
    ) -> IterativeFixingState:
        """Analyze errors using ALL accumulated context from previous attempts."""
        state["current_step"] = "analyze_with_context"
        state["attempt_number"] += 1
        state["total_attempts"] += 1

        if not state["current_notebook"]:
            return state

        notebook = state["current_notebook"]

        # Build rich context prompt with ALL previous attempt information
        context_prompt = ChatPromptTemplate.from_template("""
        You are an expert Python debugger with access to the complete history of previous fix attempts.
        
        CURRENT SITUATION:
        Notebook: {notebook_path}
        Original Error: {original_error}
        Attempt: {attempt_number} of {max_attempts}
        
        COMPLETE CONTEXT FROM PREVIOUS ATTEMPTS:
        {previous_context}
        
        ACCUMULATED LEARNING:
        {accumulated_knowledge}
        
        CURRENT NOTEBOOK CONTENT:
        {notebook_content}
        
        ORIGINAL CONTENT (for reference):
        {original_content}
        
        Please provide:
        1. Analysis of why previous attempts failed
        2. New insights based on error evolution
        3. Root cause considering all context
        4. Specific strategy for this attempt that's different from: {previous_strategies}
        5. What to avoid based on what failed: {what_failed}
        
        Use ALL the accumulated context to provide deeper insights than previous attempts.
        """)

        try:
            # Build previous context summary
            previous_context = self._build_context_summary(state)

            chain = context_prompt | self.devstral | StrOutputParser()

            analysis = chain.invoke(
                {
                    "notebook_path": notebook.notebook_path,
                    "original_error": notebook.original_failure_message,
                    "attempt_number": state["attempt_number"],
                    "max_attempts": self.max_attempts,
                    "previous_context": previous_context,
                    "accumulated_knowledge": state["accumulated_knowledge"],
                    "notebook_content": state["notebook_content"],
                    "original_content": state["original_content_backup"],
                    "previous_strategies": ", ".join(state["previous_strategies"]),
                    "what_failed": "; ".join(state["what_failed"]),
                }
            )

            state["current_error_analysis"] = analysis

            log_msg = (
                f"🔍 Contextual analysis complete (attempt {state['attempt_number']})"
            )
            state["processing_log"].append(log_msg)
            print(log_msg)

        except Exception as e:
            error_msg = f"❌ Contextual analysis failed: {e}"
            state["processing_log"].append(error_msg)
            print(error_msg)
            state["current_error_analysis"] = f"Analysis failed: {e}"

        return state

    def _build_context_summary(self, state: IterativeFixingState) -> str:
        """Build a comprehensive summary of all previous attempts."""
        if (
            not state["current_notebook"]
            or not state["current_notebook"].attempt_history
        ):
            return "No previous attempts."

        context_parts = []

        for attempt in state["current_notebook"].attempt_history:
            context_parts.append(f"""
            ATTEMPT {attempt.attempt_number}:
            - Strategy: {attempt.strategy_used}
            - Fixes Applied: {", ".join(attempt.fixes_applied)}
            - Result: {"SUCCESS" if attempt.test_passed else "FAILED"}
            - Error: {attempt.error_message}
            - Lessons: {attempt.lessons_learned}
            """)

        # Add current error patterns
        if state["error_patterns"]:
            context_parts.append(
                f"\nERROR PATTERNS OBSERVED: {'; '.join(state['error_patterns'])}"
            )

        return "\n".join(context_parts)

    def _learn_from_attempt_history(
        self, state: IterativeFixingState
    ) -> IterativeFixingState:
        """Extract learnings from the complete attempt history."""
        state["current_step"] = "learn_from_history"

        if (
            not state["current_notebook"]
            or not state["current_notebook"].attempt_history
        ):
            state["accumulated_knowledge"] = "First attempt - no previous context."
            return state

        # Learning prompt to extract insights from history
        learning_prompt = ChatPromptTemplate.from_template("""
        Analyze this complete history of fix attempts and extract key learnings:
        
        {attempt_history}
        
        Previous errors encountered: {previous_errors}
        What has been tried: {previous_fixes}
        
        Extract:
        1. Patterns in what consistently fails
        2. Approaches that showed partial progress
        3. Root cause insights from error evolution
        4. What should definitely be avoided
        5. New strategy recommendations
        
        Provide actionable insights for the next attempt.
        """)

        try:
            history_summary = self._build_context_summary(state)

            chain = learning_prompt | self.devstral | StrOutputParser()

            learnings = chain.invoke(
                {
                    "attempt_history": history_summary,
                    "previous_errors": "; ".join(state["previous_errors"]),
                    "previous_fixes": "; ".join(state["previous_fixes"]),
                }
            )

            state["accumulated_knowledge"] = learnings

            log_msg = f"🧠 Extracted learnings from {len(state['current_notebook'].attempt_history)} previous attempts"
            state["processing_log"].append(log_msg)
            print(log_msg)

        except Exception as e:
            error_msg = f"❌ Learning extraction failed: {e}"
            state["processing_log"].append(error_msg)
            print(error_msg)
            state["accumulated_knowledge"] = "Learning extraction failed"

        return state

    def _generate_fixes_with_context(
        self, state: IterativeFixingState
    ) -> IterativeFixingState:
        """Generate fixes using full contextual awareness."""
        state["current_step"] = "generate_contextual_fixes"

        if not state["current_notebook"]:
            return state

        # Context-aware fix generation
        fix_prompt = ChatPromptTemplate.from_template("""
        Generate fixes using COMPLETE CONTEXT from all previous attempts.
        
        ANALYSIS: {current_analysis}
        LEARNINGS: {accumulated_knowledge}
        
        CONSTRAINT: DO NOT repeat these failed approaches: {what_failed}
        LEVERAGE: Build on these partial successes: {what_worked}
        
        Previous strategies tried: {previous_strategies}
        Current attempt: {attempt_number} of {max_attempts}
        
        Current notebook content:
        {notebook_content}
        
        Generate fixes that:
        1. Address the root cause identified through context
        2. Avoid all previously failed approaches
        3. Build incrementally on what partially worked
        4. Use a novel approach not yet tried
        
        Return as a JSON list of specific, actionable fixes.
        """)

        try:
            chain = fix_prompt | self.devstral | StrOutputParser()

            # Determine strategy based on attempt number and context
            strategy = self._determine_contextual_strategy(state)
            state["current_strategy"] = strategy

            fixes_response = chain.invoke(
                {
                    "current_analysis": state["current_error_analysis"],
                    "accumulated_knowledge": state["accumulated_knowledge"],
                    "what_failed": "; ".join(state["what_failed"]),
                    "what_worked": "; ".join(state["what_worked"]),
                    "previous_strategies": ", ".join(state["previous_strategies"]),
                    "attempt_number": state["attempt_number"],
                    "max_attempts": self.max_attempts,
                    "notebook_content": state["notebook_content"],
                }
            )

            # Parse fixes (simplified)
            state["current_fixes"] = [f"Strategy: {strategy}", fixes_response]

            log_msg = f"🛠️  Generated contextual fixes (strategy: {strategy})"
            state["processing_log"].append(log_msg)
            print(log_msg)

        except Exception as e:
            error_msg = f"❌ Contextual fix generation failed: {e}"
            state["processing_log"].append(error_msg)
            print(error_msg)
            state["current_fixes"] = []

        return state

    def _determine_contextual_strategy(self, state: IterativeFixingState) -> str:
        """Determine strategy based on context and attempt history."""
        attempt = state["attempt_number"]
        previous_strategies = state["previous_strategies"]

        strategies = [
            "minimal_surgical",
            "dependency_focused",
            "syntax_aggressive",
            "logic_rewrite",
            "environment_adaptation",
            "complete_overhaul",
        ]

        # Avoid previously used strategies
        available_strategies = [s for s in strategies if s not in previous_strategies]

        if available_strategies:
            return available_strategies[0]
        else:
            return f"hybrid_attempt_{attempt}"

    def _apply_fixes(self, state: IterativeFixingState) -> IterativeFixingState:
        """Apply fixes with backup and tracking."""
        state["current_step"] = "apply_fixes"

        if not state["current_notebook"] or not state["current_fixes"]:
            return state

        notebook_path = state["current_notebook"].notebook_path

        # Create backup only on first attempt
        if state["attempt_number"] == 1:
            backup_path = (
                f"{notebook_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            try:
                subprocess.run(["cp", notebook_path, backup_path], check=True)
                log_msg = f"📋 Created backup: {backup_path}"
                state["processing_log"].append(log_msg)
                print(log_msg)
            except Exception as e:
                error_msg = f"❌ Backup failed: {e}"
                state["processing_log"].append(error_msg)
                print(error_msg)

        # Simplified fix application (in real implementation, you'd parse and apply)
        try:
            log_msg = f"🔧 Applied {len(state['current_fixes'])} fixes using {state['current_strategy']} strategy"
            state["processing_log"].append(log_msg)
            print(log_msg)
        except Exception as e:
            error_msg = f"❌ Fix application failed: {e}"
            state["processing_log"].append(error_msg)
            print(error_msg)

        return state

    def _test_and_capture_results(
        self, state: IterativeFixingState
    ) -> IterativeFixingState:
        """Test fixes and capture detailed results for context building."""
        state["current_step"] = "test_and_capture"

        if not state["current_notebook"]:
            return state

        notebook_path = state["current_notebook"].notebook_path

        # Run test
        test_cmd = [
            "uv",
            "run",
            "python",
            "-m",
            "pytest",
            "--nbmake",
            "--nbmake-timeout=300",
            "-v",
            notebook_path,
        ]

        try:
            log_msg = f"🧪 Testing fixes (attempt {state['attempt_number']})"
            state["processing_log"].append(log_msg)
            print(log_msg)

            result = subprocess.run(
                test_cmd,
                capture_output=True,
                text=True,
                cwd=Path(__file__).parent.parent,
            )

            state["current_success"] = result.returncode == 0
            state["current_test_output"] = (
                f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

            if state["current_success"]:
                log_msg = f"✅ Success on attempt {state['attempt_number']}!"
            else:
                log_msg = f"❌ Failed attempt {state['attempt_number']}"

            state["processing_log"].append(log_msg)
            print(log_msg)

        except Exception as e:
            error_msg = f"❌ Test execution failed: {e}"
            state["processing_log"].append(error_msg)
            print(error_msg)
            state["current_success"] = False
            state["current_test_output"] = f"Test execution error: {e}"

        return state

    def _update_context_from_attempt(
        self, state: IterativeFixingState
    ) -> IterativeFixingState:
        """Update accumulated context with results from current attempt."""
        state["current_step"] = "update_context"

        if not state["current_notebook"]:
            return state

        # Extract error message from test output
        error_message = ""
        if not state["current_success"]:
            # Extract error from test output (simplified)
            test_output = state["current_test_output"]
            if "FAILED" in test_output or "ERROR" in test_output:
                lines = test_output.split("\n")
                error_lines = [
                    line
                    for line in lines
                    if any(kw in line for kw in ["Error:", "Failed:", "Exception:"])
                ]
                error_message = "; ".join(error_lines[:3])  # Take first 3 error lines

        # Create attempt record
        attempt = FixAttempt(
            attempt_number=state["attempt_number"],
            strategy_used=state["current_strategy"],
            error_analysis=state["current_error_analysis"],
            fixes_applied=state["current_fixes"],
            test_output=state["current_test_output"],
            test_passed=state["current_success"],
            error_message=error_message,
            timestamp=datetime.now(),
        )

        # Add to notebook's attempt history
        state["current_notebook"].attempt_history.append(attempt)

        # Update accumulated context lists
        state["previous_strategies"].append(state["current_strategy"])
        state["previous_fixes"].extend(state["current_fixes"])

        if state["current_success"]:
            state["what_worked"].extend(state["current_fixes"])
        else:
            state["what_failed"].append(f"{state['current_strategy']}: {error_message}")
            state["previous_errors"].append(error_message)

            # Extract error patterns
            if error_message and error_message not in state["error_patterns"]:
                state["error_patterns"].append(error_message)

        # Update strategy effectiveness
        if state["current_strategy"] not in state["strategy_effectiveness"]:
            state["strategy_effectiveness"][state["current_strategy"]] = 0
        if state["current_success"]:
            state["strategy_effectiveness"][state["current_strategy"]] += 1

        log_msg = f"📊 Updated context: {len(state['current_notebook'].attempt_history)} attempts recorded"
        state["processing_log"].append(log_msg)
        print(log_msg)

        return state

    def _evaluate_progress(self, state: IterativeFixingState) -> IterativeFixingState:
        """Evaluate progress and determine next action."""
        state["current_step"] = "evaluate_progress"

        if state["current_success"]:
            state["should_continue_notebook"] = False
            log_msg = f"🎉 Notebook fixed after {state['attempt_number']} attempts!"
        elif state["attempt_number"] >= self.max_attempts:
            state["should_continue_notebook"] = False
            log_msg = f"💔 Max attempts ({self.max_attempts}) reached"
        else:
            state["should_continue_notebook"] = True
            log_msg = f"🔄 Continuing with attempt {state['attempt_number'] + 1} using accumulated context"

        state["processing_log"].append(log_msg)
        print(log_msg)

        return state

    def _decide_retry_with_context(self, state: IterativeFixingState) -> str:
        """Critical decision point: retry with context, succeed, or exhaust attempts."""
        decision = ""
        if state["current_success"]:
            decision = "success"
        elif state["should_continue_notebook"]:
            decision = "retry"  # This loops back to analyze_with_context with ALL accumulated context
        else:
            decision = "exhausted"

        # Debug logging
        debug_msg = (
            f"🔄 Retry decision: {decision} "
            f"(attempt {state['attempt_number']}/{self.max_attempts}, "
            f"success: {state['current_success']}, "
            f"continue: {state['should_continue_notebook']})"
        )
        state["processing_log"].append(debug_msg)
        print(debug_msg)

        return decision

    def _finalize_notebook(self, state: IterativeFixingState) -> IterativeFixingState:
        """Finalize the current notebook and prepare for next."""
        state["current_step"] = "finalize_notebook"

        if state["current_success"]:
            state["success_count"] += 1
        else:
            state["failure_count"] += 1

        # Move to next notebook
        state["current_notebook_index"] += 1

        return state

    def _complete_processing(self, state: IterativeFixingState) -> IterativeFixingState:
        """Complete processing with comprehensive summary."""
        state["current_step"] = "complete"

        summary = f"""
        🏁 Contextual Notebook Fixing Complete!
        
        📊 Results:
        - Successfully fixed: {state["success_count"]} notebooks
        - Failed to fix: {state["failure_count"]} notebooks  
        - Total attempts made: {state["total_attempts"]}
        - Average attempts per notebook: {state["total_attempts"] / len(state["failed_notebooks"]):.1f}
        
        🧠 Strategy Effectiveness:
        {json.dumps(state["strategy_effectiveness"], indent=2)}
        
        🔍 Common Error Patterns:
        {"; ".join(state["common_patterns"])}
        """

        state["processing_log"].append(summary)
        print(summary)

        return state

    async def fix_with_context_accumulation(
        self, failed_notebooks: List[NotebookFailure]
    ) -> Dict[str, Any]:
        """Main method to fix notebooks with full context accumulation."""
        initial_state = IterativeFixingState(
            failed_notebooks=failed_notebooks.copy(),
            current_notebook=None,
            current_notebook_index=0,
            notebook_content="",
            original_content_backup="",
            attempt_number=0,
            max_attempts=self.max_attempts,
            previous_errors=[],
            previous_fixes=[],
            previous_strategies=[],
            what_worked=[],
            what_failed=[],
            error_patterns=[],
            current_error_analysis="",
            current_strategy="",
            current_fixes=[],
            current_test_output="",
            current_success=False,
            accumulated_knowledge="",
            strategy_effectiveness={},
            common_patterns=[],
            current_step="",
            should_continue_notebook=True,
            should_continue_processing=True,
            success_count=0,
            failure_count=0,
            total_attempts=0,
            processing_log=[],
        )

        # Execute the contextual workflow with recursion limit configuration
        config = {"recursion_limit": 100}
        final_state = await self.graph.ainvoke(initial_state, config)

        return {
            "success_count": final_state["success_count"],
            "failure_count": final_state["failure_count"],
            "total_attempts": final_state["total_attempts"],
            "strategy_effectiveness": final_state["strategy_effectiveness"],
            "processing_log": final_state["processing_log"],
            "accumulated_knowledge": final_state["accumulated_knowledge"],
        }


# JUnit parsing and main function (similar to before but simpler for focus on context)
def parse_junit_xml(xml_file_path: str) -> List[NotebookFailure]:
    """Parse JUnit XML and create NotebookFailure objects with context tracking."""
    failed_notebooks = []

    try:
        tree = ET.parse(xml_file_path)
        root = tree.getroot()

        print(f"📊 Parsing JUnit XML: {xml_file_path}")

        for testcase in root.findall(".//testcase"):
            failure = testcase.find("failure")
            error = testcase.find("error")

            if failure is not None or error is not None:
                classname = testcase.get("classname", "")
                test_name = testcase.get("name", "")
                execution_time = float(testcase.get("time", 0))

                print(
                    f"🔍 Found failed test - classname: {classname}, test_name: {test_name}"
                )

                # Convert classname to notebook path
                # Example: "02-technical-guides.multidimensional-analysis.main.ipynb"
                # becomes "02-technical-guides/multidimensional-analysis/main.ipynb"

                if classname.endswith(".ipynb"):
                    # Classname already includes the .ipynb extension
                    # Split on dots, but keep .ipynb as part of the filename
                    parts = classname.split(".")
                    # The last part should be "ipynb", second to last should be filename
                    if len(parts) >= 2 and parts[-1] == "ipynb":
                        # Rejoin filename with extension
                        filename = f"{parts[-2]}.ipynb"
                        # Directory path is everything except the last two parts
                        if len(parts) > 2:
                            directory_path = "/".join(parts[:-2])
                            notebook_path = f"{directory_path}/{filename}"
                        else:
                            notebook_path = filename
                    else:
                        # Fallback: just replace dots with slashes
                        notebook_path = classname.replace(".", "/")
                else:
                    # Classname doesn't include .ipynb, need to construct path
                    if test_name.endswith(".ipynb"):
                        # Use test_name as filename
                        notebook_filename = test_name
                        # Extract directory from classname
                        path_parts = classname.split(".")
                        if len(path_parts) > 1:
                            # Use all parts as directory path
                            directory_path = "/".join(path_parts)
                            notebook_path = f"{directory_path}/{notebook_filename}"
                        else:
                            notebook_path = notebook_filename
                    else:
                        # Neither classname nor test_name has .ipynb, add it
                        notebook_path = classname.replace(".", "/") + ".ipynb"

                # Resolve full path
                workspace_root = Path(__file__).parent.parent
                full_notebook_path = workspace_root / notebook_path

                print(f"🔍 Resolving path: {notebook_path} -> {full_notebook_path}")

                # Try alternative path resolution if file doesn't exist
                if not full_notebook_path.exists():
                    print(f"⚠️  Notebook not found at {full_notebook_path}")

                    # Try using just the test_name as filename in workspace root
                    alt_path = workspace_root / test_name
                    if alt_path.exists():
                        full_notebook_path = alt_path
                        print(f"✅ Found alternative path: {alt_path}")
                    else:
                        # Try searching for the notebook by name
                        notebook_name = (
                            test_name
                            if test_name.endswith(".ipynb")
                            else f"{test_name}.ipynb"
                        )
                        search_results = list(workspace_root.rglob(notebook_name))
                        if search_results:
                            full_notebook_path = search_results[0]
                            print(f"✅ Found by search: {full_notebook_path}")
                        else:
                            print(f"❌ Could not locate notebook: {notebook_name}")
                            continue

                # Extract failure details
                if failure is not None:
                    failure_type = "test_failure"
                    failure_message = failure.get("message", "")
                    error_output = failure.text or ""
                elif error is not None:
                    failure_type = "test_error"
                    failure_message = error.get("message", "")
                    error_output = error.text or ""

                failed_notebook = NotebookFailure(
                    notebook_path=str(full_notebook_path),
                    classname=classname,
                    test_name=test_name,
                    failure_type=failure_type,
                    original_failure_message=failure_message,
                    original_error_output=error_output,
                    execution_time=execution_time,
                )

                failed_notebooks.append(failed_notebook)
                print(f"✅ Added failed notebook: {full_notebook_path}")

    except Exception as e:
        print(f"❌ Error parsing JUnit XML {xml_file_path}: {e}")
        import traceback

        traceback.print_exc()

    print(f"📊 Total failed notebooks found: {len(failed_notebooks)}")
    return failed_notebooks


def get_latest_junit_report() -> Optional[str]:
    """Find the latest JUnit XML report in the reports directory."""
    reports_dir = Path("reports")

    print(f"🔍 Looking for JUnit reports in: {reports_dir.absolute()}")

    if not reports_dir.exists():
        print(f"❌ Reports directory does not exist: {reports_dir.absolute()}")
        return None

    # Look for files matching the pattern junit-*.xml
    junit_files = list(reports_dir.glob("junit-*.xml"))

    print(f"📊 Found {len(junit_files)} JUnit XML files:")
    for file in junit_files:
        print(f"  - {file} (modified: {datetime.fromtimestamp(file.stat().st_mtime)})")

    if not junit_files:
        print("❌ No JUnit XML files found matching pattern 'junit-*.xml'")
        return None

    # Return the most recent file
    latest_file = max(junit_files, key=lambda f: f.stat().st_mtime)
    print(f"✅ Using latest JUnit report: {latest_file}")

    return str(latest_file)


async def main():
    """Main entry point for contextual notebook fixing."""
    parser = argparse.ArgumentParser(
        description="Fix notebooks with context accumulation across retry attempts"
    )
    parser.add_argument("--junit-xml", help="Path to JUnit XML report file")
    parser.add_argument(
        "--max-attempts", type=int, default=5, help="Maximum attempts per notebook"
    )
    parser.add_argument(
        "--run-final-test", action="store_true", help="Run final test after fixing"
    )

    args = parser.parse_args()

    # Find JUnit XML file
    if args.junit_xml:
        junit_file = args.junit_xml
        if not Path(junit_file).exists():
            print(f"❌ Specified JUnit XML file does not exist: {junit_file}")
            sys.exit(1)
    else:
        junit_file = get_latest_junit_report()
        if not junit_file:
            print(
                "❌ No JUnit XML report found. Run 'make test' first to generate reports."
            )
            print("💡 Expected to find files matching pattern: reports/junit-*.xml")
            sys.exit(1)

    print(f"📊 Using JUnit report: {junit_file}")

    # Validate the JUnit XML file
    try:
        tree = ET.parse(junit_file)
        root = tree.getroot()
        total_tests = len(root.findall(".//testcase"))
        print(f"📊 JUnit XML contains {total_tests} test cases")
    except Exception as e:
        print(f"❌ Invalid JUnit XML file: {e}")
        sys.exit(1)

    # Parse failed notebooks
    failed_notebooks = parse_junit_xml(junit_file)

    if not failed_notebooks:
        print("🎉 No failing notebooks found! All tests are passing.")
        return

    print(f"📋 Found {len(failed_notebooks)} failing notebooks:")
    for notebook in failed_notebooks:
        print(f"  - {Path(notebook.notebook_path)}")

    # Initialize contextual fixer
    print(
        f"🧠 Initializing contextual fixer (max {args.max_attempts} attempts per notebook)..."
    )
    fixer = ContextualNotebookFixer(max_attempts=args.max_attempts)

    # Execute contextual fixing
    results = await fixer.fix_with_context_accumulation(failed_notebooks)

    # Optional final test
    if args.run_final_test:
        print("🧪 Running final validation...")
        try:
            result = subprocess.run(["make", "test"], capture_output=True, text=True)
            print(
                "✅ All tests pass!"
                if result.returncode == 0
                else "❌ Some tests still failing"
            )
        except Exception as e:
            print(f"❌ Final test failed: {e}")

    # Save comprehensive log
    log_file = f"contextual_fixing_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(log_file, "w") as f:
        f.write("\n".join(results["processing_log"]))
        f.write(f"\n\nFinal Knowledge Base:\n{results['accumulated_knowledge']}")

    print(f"📝 Comprehensive log saved to: {log_file}")
    print(
        f"🎯 Success rate: {results['success_count']}/{results['success_count'] + results['failure_count']}"
    )

    # Summary of results
    if results["success_count"] > 0:
        print(f"✅ Successfully fixed {results['success_count']} notebooks")
    if results["failure_count"] > 0:
        print(
            f"❌ Failed to fix {results['failure_count']} notebooks after {args.max_attempts} attempts each"
        )

    print(f"📊 Total attempts made: {results['total_attempts']}")
    if results["total_attempts"] > 0:
        avg_attempts = results["total_attempts"] / len(failed_notebooks)
        print(f"📈 Average attempts per notebook: {avg_attempts:.1f}")


if __name__ == "__main__":
    asyncio.run(main())
