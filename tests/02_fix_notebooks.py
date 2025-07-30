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
import subprocess
import sys
import xml.etree.ElementTree as ET
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, TypedDict, Any
from datetime import datetime
import subprocess
import re
import os

# LangFuse integration for comprehensive observability
try:
    from langfuse import Langfuse, observe

    LANGFUSE_AVAILABLE = True
    print("📊 LangFuse available for observability")
except ImportError:
    LANGFUSE_AVAILABLE = False
    print("⚠️  LangFuse not available. Install with: uv add langfuse")

    # Create mock decorators to prevent errors
    def observe(name=None, **kwargs):
        def decorator(func):
            return func

        return decorator


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

    # Working copy safety
    original_notebook_path: str


class ContextualNotebookFixer:
    """
    LangGraph-based notebook fixer that builds and maintains context
    across retry attempts, learning from each failure to improve the next attempt.

    Enhanced with LangFuse observability for comprehensive monitoring.
    """

    def __init__(self, max_attempts: int = 5):
        self.max_attempts = max_attempts

        # Initialize LangFuse for observability
        self.langfuse = None
        if LANGFUSE_AVAILABLE:
            try:
                # Initialize LangFuse client
                self.langfuse = Langfuse(
                    public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
                    secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
                    host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
                )

                print("✅ LangFuse observability initialized")

                # Create a session for this notebook fixing run
                self.session_id = (
                    f"notebook-fixing-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                )

            except Exception as e:
                print(f"⚠️  LangFuse initialization failed: {e}")
                self.langfuse = None

        # Initialize ChatOllama
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
        workflow.add_node("apply_fixes_nbdime", self._apply_fixes_with_nbdime)
        workflow.add_node("test_with_pytest", self._test_with_pytest)
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
        workflow.add_edge("generate_contextual_fixes", "apply_fixes_nbdime")
        workflow.add_edge("apply_fixes_nbdime", "test_with_pytest")
        workflow.add_edge("test_with_pytest", "update_context")
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
        """Prepare notebook context by creating a working copy."""
        state["current_step"] = "prepare_notebook"

        if not state["current_notebook"]:
            return state

        original_notebook_path = state["current_notebook"].notebook_path

        # Create a working copy with -fix suffix before the extension
        path_parts = original_notebook_path.rsplit(".", 1)
        if len(path_parts) == 2:
            working_notebook_path = f"{path_parts[0]}-fix.{path_parts[1]}"
        else:
            working_notebook_path = f"{original_notebook_path}-fix"

        try:
            # Copy original to working file
            subprocess.run(
                ["cp", original_notebook_path, working_notebook_path], check=True
            )

            # Update the notebook path to point to the working copy
            state["current_notebook"].notebook_path = working_notebook_path

            # Load content from the working copy
            with open(working_notebook_path, "r", encoding="utf-8") as f:
                content = f.read()
                state["notebook_content"] = content
                state["original_content_backup"] = content

            # Store the original path for reference
            state["original_notebook_path"] = original_notebook_path

            log_msg = f"📄 Created working copy: {working_notebook_path}"
            state["processing_log"].append(log_msg)
            print(log_msg)

            log_msg = f"📖 Loaded notebook content: {len(content)} characters"
            state["processing_log"].append(log_msg)
            print(log_msg)

        except Exception as e:
            error_msg = f"❌ Failed to create working copy or load notebook: {e}"
            state["processing_log"].append(error_msg)
            print(error_msg)
            state["notebook_content"] = ""
            state["original_content_backup"] = ""

        return state

    @(
        observe(name="analyze_with_accumulated_context")
        if LANGFUSE_AVAILABLE
        else lambda x: x
    )
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

        print(f"\n🔍 ERROR ANALYSIS - Attempt {state['attempt_number']}")
        print(f"📂 Notebook: {notebook.notebook_path}")
        print(f"🎯 Original Error Type: {notebook.failure_type}")
        print("=" * 80)

        # Display the original error for context
        print("❌ ORIGINAL ERROR MESSAGE:")
        print("-" * 40)
        print(
            notebook.original_failure_message[:500] + "..."
            if len(notebook.original_failure_message) > 500
            else notebook.original_failure_message
        )

        print("\n📜 ORIGINAL ERROR OUTPUT:")
        print("-" * 40)
        print(
            notebook.original_error_output[:800] + "..."
            if len(notebook.original_error_output) > 800
            else notebook.original_error_output
        )

        # Show previous attempts context
        if state["attempt_number"] > 1:
            print(
                f"\n🧠 PREVIOUS ATTEMPTS CONTEXT ({len(state['previous_errors'])} previous errors):"
            )
            print("-" * 40)
            for i, prev_error in enumerate(
                state["previous_errors"][-3:], 1
            ):  # Show last 3
                print(f"  {i}. {prev_error[:150]}...")

            print(f"\n📚 WHAT HAS BEEN TRIED:")
            for i, strategy in enumerate(state["previous_strategies"], 1):
                print(f"  {i}. {strategy}")

            if state["what_failed"]:
                print(f"\n❌ WHAT FAILED:")
                for i, failure in enumerate(
                    state["what_failed"][-3:], 1
                ):  # Show last 3
                    print(f"  {i}. {failure[:100]}...")

        # Add LangFuse observability - create trace span manually
        span = None
        if LANGFUSE_AVAILABLE and self.langfuse:
            try:
                span = self.langfuse.start_as_current_span(
                    name=f"contextual_analysis_attempt_{state['attempt_number']}",
                    metadata={
                        "notebook_path": notebook.notebook_path,
                        "attempt_number": state["attempt_number"],
                        "max_attempts": self.max_attempts,
                        "total_attempts": state["total_attempts"],
                        "previous_attempts_count": len(state["previous_errors"]),
                        "accumulated_knowledge_length": len(
                            state["accumulated_knowledge"]
                        ),
                        "strategy_effectiveness": state["strategy_effectiveness"],
                        "original_error_type": notebook.failure_type,
                        "original_error_length": len(notebook.original_failure_message),
                    },
                )
            except Exception as e:
                print(f"⚠️  LangFuse span creation failed: {e}")

        # Build rich context prompt with ALL previous attempt information
        context_prompt = ChatPromptTemplate.from_template("""
        You are an expert Python debugger with access to the complete history of previous fix attempts.
        
        CURRENT SITUATION:
        Notebook: {notebook_path}
        Original Error Type: {error_type}
        Original Error: {original_error}
        Original Error Output: {original_error_output}
        Current Error Context: {current_error_context}
        Attempt: {attempt_number} of {max_attempts}
        
        COMPLETE CONTEXT FROM PREVIOUS ATTEMPTS:
        {previous_context}
        
        ACCUMULATED LEARNING:
        {accumulated_knowledge}
        
        CURRENT NOTEBOOK CONTENT (first 2000 chars):
        {notebook_content}
        
        ORIGINAL CONTENT (for reference):
        {original_content}
        
        Please provide:
        1. Deep analysis of the root cause considering the error type and output
        2. Analysis of why previous attempts failed (if any)
        3. New insights based on error evolution across attempts
        4. Root cause considering all context and error patterns
        5. Specific strategy for this attempt that's different from: {previous_strategies}
        6. What to avoid based on what failed: {what_failed}
        7. Key code sections that likely need modification
        8. If there's a NEW current error, focus on that rather than the original
        
        Use ALL the accumulated context to provide deeper insights than previous attempts.
        Focus on the specific error details and notebook content to identify the exact issue.
        If the current error is different from the original, analyze the progression and what the fixes achieved.
        """)

        try:
            # Build previous context summary
            previous_context = self._build_context_summary(state)

            chain = context_prompt | self.devstral | StrOutputParser()

            print("\n🤖 REQUESTING DEVSTRAL ANALYSIS...")
            print(
                "   Sending context, error details, and notebook content to Devstral..."
            )

            # Use current error context if available, otherwise fall back to original
            current_error = (
                state["current_notebook"].current_error_context
                if state["current_notebook"].current_error_context
                else state["current_notebook"].original_failure_message
            )

            analysis = chain.invoke(
                {
                    "notebook_path": notebook.notebook_path,
                    "error_type": notebook.failure_type,
                    "original_error": notebook.original_failure_message,
                    "original_error_output": notebook.original_error_output,
                    "current_error_context": current_error,
                    "attempt_number": state["attempt_number"],
                    "max_attempts": self.max_attempts,
                    "previous_context": previous_context,
                    "accumulated_knowledge": state["accumulated_knowledge"],
                    "notebook_content": state["notebook_content"][:2000] + "..."
                    if len(state["notebook_content"]) > 2000
                    else state["notebook_content"],
                    "original_content": state["original_content_backup"][:2000] + "..."
                    if len(state["original_content_backup"]) > 2000
                    else state["original_content_backup"],
                    "previous_strategies": ", ".join(state["previous_strategies"]),
                    "what_failed": "; ".join(state["what_failed"]),
                }
            )

            state["current_error_analysis"] = analysis

            print("\n📋 DEVSTRAL'S ERROR ANALYSIS:")
            print("-" * 60)
            print(analysis)
            print("-" * 60)

            # Update LangFuse span with results
            if span:
                try:
                    self.langfuse.update_current_span(
                        output={
                            "analysis_length": len(analysis),
                            "previous_context_length": len(previous_context),
                            "analysis_preview": analysis[:500],
                            "success": True,
                        }
                    )
                except Exception as e:
                    print(f"⚠️  LangFuse span update failed: {e}")

            log_msg = (
                f"🔍 Contextual analysis complete (attempt {state['attempt_number']})"
            )
            state["processing_log"].append(log_msg)
            print(f"\n✅ {log_msg}")

        except Exception as e:
            error_msg = f"❌ Contextual analysis failed: {e}"
            state["processing_log"].append(error_msg)
            print(error_msg)
            state["current_error_analysis"] = f"Analysis failed: {e}"

        print("=" * 80)
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

    @observe(name="generate_fixes_with_context") if LANGFUSE_AVAILABLE else lambda x: x
    def _generate_fixes_with_context(
        self, state: IterativeFixingState
    ) -> IterativeFixingState:
        """Generate fixes using full contextual awareness."""
        state["current_step"] = "generate_contextual_fixes"

        if not state["current_notebook"]:
            return state

        # Add LangFuse observability - create trace span manually
        span = None
        if LANGFUSE_AVAILABLE and self.langfuse:
            try:
                span = self.langfuse.start_as_current_span(
                    name=f"fix_generation_attempt_{state['attempt_number']}",
                    metadata={
                        "notebook_path": state["current_notebook"].notebook_path
                        if state["current_notebook"]
                        else "unknown",
                        "attempt_number": state["attempt_number"],
                        "previous_strategies": state["previous_strategies"],
                        "what_failed_count": len(state["what_failed"]),
                        "what_worked_count": len(state["what_worked"]),
                        "accumulated_knowledge_length": len(
                            state["accumulated_knowledge"]
                        ),
                    },
                )
            except Exception as e:
                print(f"⚠️  LangFuse span creation failed: {e}")

        # Enhanced prompt that asks for specific code changes
        fix_prompt = ChatPromptTemplate.from_template("""
        You are fixing a Jupyter notebook. Provide specific, actionable code changes.
        
        CURRENT ERROR ANALYSIS: {current_analysis}
        ACCUMULATED LEARNING: {accumulated_knowledge}
        
        CONSTRAINTS:
        - DO NOT repeat these failed approaches: {what_failed}
        - Build on these partial successes: {what_worked}
        - Previous strategies tried: {previous_strategies}
        
        CURRENT NOTEBOOK CONTENT:
        {notebook_content}
        
        ORIGINAL ERROR:
        {original_error}
        
        Please provide:
        1. SPECIFIC CODE SECTIONS that need to be changed (show the exact problematic code)
        2. EXACT REPLACEMENT CODE for each section
        3. EXPLANATION of why each change addresses the error
        4. LINE NUMBERS or unique identifiers where changes should be made
        
        Format your response as:
        
        ## PROBLEM ANALYSIS
        [Brief analysis of the root cause]
        
        ## CODE CHANGES
        
        ### Change 1: [Description]
        **Original code (to be replaced):**
        ```python
        [exact code to find and replace]
        ```
        
        **New code:**
        ```python
        [exact replacement code]
        ```
        
        **Reason:** [Why this change fixes the issue]
        
        ### Change 2: [Description]
        [Continue for each change needed]
        
        ## VERIFICATION
        [How to verify the fix works]
        """)

        try:
            chain = fix_prompt | self.devstral | StrOutputParser()

            # Determine strategy based on attempt number and context
            strategy = self._determine_contextual_strategy(state)
            state["current_strategy"] = strategy

            print(f"\n🔧 DEVSTRAL FIX GENERATION - Attempt {state['attempt_number']}")
            print(f"📋 Strategy: {strategy}")
            print(f"📂 Notebook: {state['current_notebook'].notebook_path}")
            print("=" * 80)

            fixes_response = chain.invoke(
                {
                    "current_analysis": state["current_error_analysis"],
                    "accumulated_knowledge": state["accumulated_knowledge"],
                    "what_failed": "; ".join(state["what_failed"]),
                    "what_worked": "; ".join(state["what_worked"]),
                    "previous_strategies": ", ".join(state["previous_strategies"]),
                    "attempt_number": state["attempt_number"],
                    "max_attempts": self.max_attempts,
                    "notebook_content": state["notebook_content"][:2000] + "..."
                    if len(state["notebook_content"]) > 2000
                    else state["notebook_content"],
                    "original_error": state[
                        "current_notebook"
                    ].original_failure_message,
                }
            )

            # Display the detailed fix response
            print("🤖 DEVSTRAL'S PROPOSED FIXES:")
            print("-" * 60)
            print(fixes_response)
            print("-" * 60)

            # Store the detailed fixes
            state["current_fixes"] = [f"Strategy: {strategy}", fixes_response]

            # Parse and extract specific code changes for enhanced logging
            code_changes = self._extract_code_changes(fixes_response)
            if code_changes:
                print(f"\n📝 EXTRACTED CODE CHANGES ({len(code_changes)} changes):")
                for i, change in enumerate(code_changes, 1):
                    print(
                        f"\n  Change {i}: {change.get('description', 'No description')}"
                    )
                    if change.get("original_code"):
                        print(f"    ❌ Original: {change['original_code'][:100]}...")
                    if change.get("new_code"):
                        print(f"    ✅ New: {change['new_code'][:100]}...")
                    if change.get("reason"):
                        print(f"    💡 Reason: {change['reason']}")

            # Update LangFuse span with detailed results
            if span:
                try:
                    self.langfuse.update_current_span(
                        output={
                            "strategy_selected": strategy,
                            "fixes_count": len(state["current_fixes"]),
                            "fixes_response_length": len(fixes_response),
                            "code_changes_extracted": len(code_changes)
                            if code_changes
                            else 0,
                            "detailed_fixes": fixes_response[:1000],  # First 1000 chars
                            "success": True,
                        }
                    )
                except Exception as e:
                    print(f"⚠️  LangFuse span update failed: {e}")

            log_msg = f"🛠️  Generated {len(code_changes) if code_changes else 0} specific code changes using {strategy} strategy"
            state["processing_log"].append(log_msg)
            print(f"\n{log_msg}")

        except Exception as e:
            error_msg = f"❌ Contextual fix generation failed: {e}"
            state["processing_log"].append(error_msg)
            print(error_msg)
            state["current_fixes"] = []

            # Update LangFuse span with error
            if span:
                try:
                    self.langfuse.update_current_span(
                        output={"error": str(e), "success": False}
                    )
                except Exception as e2:
                    print(f"⚠️  LangFuse error logging failed: {e2}")

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

    def _extract_code_changes(self, fixes_response: str) -> List[Dict[str, str]]:
        """Extract specific code changes from Devstral's response."""
        changes = []

        # Debug: Let's see what we're trying to parse
        print(f"\n🔍 DEBUG: Parsing fixes response (length: {len(fixes_response)})")
        print(f"    First 200 chars: {fixes_response[:200]}...")

        # Look for code blocks in the response
        # Updated pattern to handle the actual format from Devstral
        change_pattern = r"### Change \d+:([^#]*?)(?=### Change \d+:|## VERIFICATION|$)"

        change_matches = re.findall(change_pattern, fixes_response, re.DOTALL)

        print(f"    Found {len(change_matches)} change matches")

        for i, change_text in enumerate(change_matches):
            change_info = {"description": f"Change {i + 1}"}

            # Extract description from the first line
            lines = change_text.strip().split("\n")
            if lines:
                change_info["description"] = lines[0].strip()

            # More flexible patterns for original and new code
            original_match = re.search(
                r"\*\*Original code.*?\*\*:.*?```python\s*(.*?)```",
                change_text,
                re.DOTALL,
            )
            if original_match:
                change_info["original_code"] = original_match.group(1).strip()
                print(
                    f"    ✅ Extracted original code: {change_info['original_code'][:50]}..."
                )

            # Extract new code
            new_match = re.search(
                r"\*\*New code.*?\*\*:.*?```python\s*(.*?)```", change_text, re.DOTALL
            )
            if new_match:
                change_info["new_code"] = new_match.group(1).strip()
                print(f"    ✅ Extracted new code: {change_info['new_code'][:50]}...")

            # Extract reason
            reason_match = re.search(
                r"\*\*Reason:\*\*\s*(.*?)(?=\n\n|$)", change_text, re.DOTALL
            )
            if reason_match:
                change_info["reason"] = reason_match.group(1).strip()

            # If we found either original or new code, add the change
            if change_info.get("original_code") or change_info.get("new_code"):
                changes.append(change_info)
                print(f"    ✅ Added change: {change_info['description']}")
            else:
                print(f"    ⚠️  No code found for: {change_info['description']}")

        # If no structured changes found, try to extract any code blocks
        if not changes:
            print("    🔍 No structured changes found, looking for any code blocks...")
            code_blocks = re.findall(r"```python\s*(.*?)```", fixes_response, re.DOTALL)
            if len(code_blocks) >= 2:
                # Assume first is original, second is new
                changes.append(
                    {
                        "description": "Code replacement from blocks",
                        "original_code": code_blocks[0].strip(),
                        "new_code": code_blocks[1].strip(),
                        "reason": "Extracted from code blocks",
                    }
                )
                print(
                    f"    ✅ Extracted from code blocks: {len(code_blocks)} blocks found"
                )

        print(f"    📋 Total changes extracted: {len(changes)}")
        return changes

    def _apply_fixes_with_nbdime(
        self, state: IterativeFixingState
    ) -> IterativeFixingState:
        """Apply fixes by properly modifying notebook cells - preserving JSON structure."""
        state["current_step"] = "apply_fixes"

        if not state["current_notebook"] or not state["current_fixes"]:
            return state

        notebook_path = state["current_notebook"].notebook_path

        print(
            f"\n🔧 APPLYING FIXES TO NOTEBOOK CELLS - Attempt {state['attempt_number']}"
        )
        print(f"📂 Working Copy: {notebook_path}")
        print("=" * 80)

        # No need to create backup since we're already working on a copy
        # The original file is safely preserved

        # Extract code changes from Devstral's response
        fixes_response = (
            state["current_fixes"][1] if len(state["current_fixes"]) > 1 else ""
        )
        code_changes = self._extract_code_changes(fixes_response)

        if not code_changes:
            print("    ⚠️  No specific code changes extracted from Devstral's response")
            return state

        print(f"\n🛠️  APPLYING {len(code_changes)} CODE CHANGES TO NOTEBOOK CELLS:")

        modifications_made = []

        try:
            # Load the notebook as JSON
            with open(notebook_path, "r", encoding="utf-8") as f:
                notebook_data = json.load(f)

            print(
                f"📖 Loaded notebook with {len(notebook_data.get('cells', []))} cells"
            )

            # Apply each code change to the appropriate cells
            for i, change in enumerate(code_changes, 1):
                original_code = change.get("original_code", "").strip()
                new_code = change.get("new_code", "").strip()
                description = change.get("description", f"Change {i}")

                # Add AI-generated comment to the new code
                if new_code:
                    new_code_with_comment = f"# THIS IS AI GENERATED\n{new_code}"
                else:
                    new_code_with_comment = new_code

                # Find and replace code in matching cells
                found_and_replaced = False
                for cell in notebook_data.get("cells", []):
                    if cell.get("cell_type") == "code":
                        cell_source = self._get_cell_source_as_string(cell)

                        if original_code and original_code in cell_source:
                            print(f"  ✅ Applying: {description}")
                            print(f"    🔍 Found: {original_code[:50]}...")
                            print(
                                f"    🔧 Replacing with: {new_code_with_comment[:50]}..."
                            )

                            updated_source = cell_source.replace(
                                original_code, new_code_with_comment
                            )
                            self._set_cell_source_from_string(cell, updated_source)
                            modifications_made.append(description)
                            found_and_replaced = True
                            break

                        elif original_code:
                            # Try to find a key line from the original code
                            lines = [
                                line.strip()
                                for line in original_code.split("\n")
                                if line.strip()
                            ]
                            if lines:
                                key_line = lines[0]
                                if key_line in cell_source:
                                    print(f"  🔍 Found key line for: {description}")
                            print(f"    � Key line: {key_line}")

                            # Replace the key line with the new code (with AI comment)
                            updated_source = cell_source.replace(
                                key_line, new_code_with_comment
                            )
                            self._set_cell_source_from_string(cell, updated_source)
                            modifications_made.append(f"{description} (key line match)")
                            found_and_replaced = True
                            break
                        else:
                            print(f"  ⚠️  Could not find code for: {description}")
                else:
                    print(f"  ⚠️  No original code specified for: {description}")

            # Save the modified notebook if we made changes
            if modifications_made:
                with open(notebook_path, "w", encoding="utf-8") as f:
                    json.dump(notebook_data, f, indent=1, ensure_ascii=False)

                print(
                    f"\n✅ Successfully applied {len(modifications_made)} modifications:"
                )
                for mod in modifications_made:
                    print(f"    ✓ {mod}")

                log_msg = f"🔧 Applied {len(modifications_made)} code changes to notebook cells"
                state["processing_log"].append(log_msg)
                print(f"\n✅ {log_msg}")

                # Update state with what was changed
                change_summary = "Applied changes: " + "; ".join(modifications_made)
                state["processing_log"].append(change_summary)

            else:
                warning_msg = "⚠️  No modifications were applied to the notebook"
                state["processing_log"].append(warning_msg)
                print(warning_msg)

        except Exception as e:
            error_msg = f"❌ Fix application failed: {e}"
            state["processing_log"].append(error_msg)
            print(error_msg)

        print("=" * 80)
        return state

    def _get_cell_source_as_string(self, cell: dict) -> str:
        """Convert notebook cell source to a single string."""
        source = cell.get("source", [])
        if isinstance(source, list):
            return "".join(source)
        elif isinstance(source, str):
            return source
        else:
            return ""

    def _set_cell_source_from_string(self, cell: dict, source_string: str):
        """Set notebook cell source from a string, maintaining notebook format."""
        # Split into lines and add newlines where needed
        lines = source_string.split("\n")

        # Convert to the list format that notebooks expect
        cell_source = []
        for i, line in enumerate(lines):
            if i == len(lines) - 1 and line == "":
                # Don't add empty string at the end
                continue
            elif i == len(lines) - 1:
                # Last line without newline
                cell_source.append(line)
            else:
                # Line with newline
                cell_source.append(line + "\n")

        cell["source"] = cell_source

    def _test_with_pytest(self, state: IterativeFixingState) -> IterativeFixingState:
        """Test the modified notebook using pytest - simple and reliable."""
        state["current_step"] = "test_with_pytest"

        if not state["current_notebook"]:
            return state

        notebook_path = state["current_notebook"].notebook_path

        print(f"\n🧪 TESTING WITH PYTEST - Attempt {state['attempt_number']}")
        print(f"📂 Notebook: {notebook_path}")
        print("=" * 80)

        # Simple pytest command
        test_cmd = [
            "uv",
            "run",
            "python",
            "-m",
            "pytest",
            "--nbmake",
            "--nbmake-timeout=300",
            "-v",
            "--tb=short",
            notebook_path,
        ]

        try:
            print(f"🧪 Running pytest on modified notebook...")

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
                print("✅ SUCCESS! Notebook runs without errors!")
                print("🎉 Devstral's fixes worked!")
                log_msg = f"✅ Success on attempt {state['attempt_number']}!"
            else:
                print("❌ FAILED - Notebook still has errors")
                print("\n📜 ERROR OUTPUT:")
                print("-" * 40)

                # Show relevant error information
                error_output = result.stderr + "\n" + result.stdout

                # Extract key error lines
                error_lines = []
                for line in error_output.split("\n"):
                    if any(
                        keyword in line.lower()
                        for keyword in [
                            "error:",
                            "traceback",
                            "failed",
                            "exception",
                            "syntaxerror",
                            "nameerror",
                        ]
                    ):
                        error_lines.append(line.strip())

                if error_lines:
                    print("Key errors found:")
                    for line in error_lines[-5:]:  # Show last 5 error lines
                        print(f"  {line}")
                else:
                    # Show last part of stderr if no specific errors found
                    if result.stderr:
                        print("Last stderr output:")
                        print(result.stderr[-300:])

                print("-" * 40)
                log_msg = f"❌ Failed attempt {state['attempt_number']}"

                # Update current error context for next iteration
                new_error = ""
                if error_lines:
                    new_error = "; ".join(error_lines[-3:])  # Take last 3 error lines

                if (
                    new_error
                    and new_error != state["current_notebook"].original_failure_message
                ):
                    print(f"\n🔄 NEW ERROR DETECTED:")
                    print(f"   {new_error[:200]}...")
                    state["current_notebook"].current_error_context = new_error

            state["processing_log"].append(log_msg)
            print(f"\n{log_msg}")

        except Exception as e:
            error_msg = f"❌ Pytest execution failed: {e}"
            state["processing_log"].append(error_msg)
            print(error_msg)
            state["current_success"] = False
            state["current_test_output"] = f"Pytest execution error: {e}"

        print("=" * 80)
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
        """Finalize the current notebook by handling working copy."""
        state["current_step"] = "finalize_notebook"

        if not state["current_notebook"]:
            return state

        working_notebook_path = state["current_notebook"].notebook_path
        original_notebook_path = state.get("original_notebook_path", "")

        try:
            if state["current_success"]:
                # Success: Keep both original and fixed copy for inspection
                log_msg = f"✅ Success! Fixed copy available for inspection: {working_notebook_path}"
                state["processing_log"].append(log_msg)
                print(log_msg)
                log_msg = f"📄 Original notebook preserved: {original_notebook_path}"
                state["processing_log"].append(log_msg)
                print(log_msg)

                state["success_count"] += 1
            else:
                # Failure: Keep working copy for inspection, preserve original
                log_msg = f"📄 Failed working copy preserved for inspection: {working_notebook_path}"
                state["processing_log"].append(log_msg)
                print(log_msg)

                # Restore original path to the notebook for reference
                if original_notebook_path:
                    state["current_notebook"].notebook_path = original_notebook_path
                    log_msg = (
                        f"📄 Original notebook preserved: {original_notebook_path}"
                    )
                    state["processing_log"].append(log_msg)
                    print(log_msg)

                state["failure_count"] += 1

        except Exception as e:
            error_msg = f"❌ Error finalizing notebook: {e}"
            state["processing_log"].append(error_msg)
            print(error_msg)
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

    @(
        observe(name="fix_with_context_accumulation")
        if LANGFUSE_AVAILABLE
        else lambda x: x
    )
    async def fix_with_context_accumulation(
        self, failed_notebooks: List[NotebookFailure]
    ) -> Dict[str, Any]:
        """Main method to fix notebooks with full context accumulation."""

        # Create LangFuse trace for the entire fixing session
        session_span = None
        if LANGFUSE_AVAILABLE and self.langfuse:
            try:
                session_span = self.langfuse.start_as_current_span(
                    name="notebook_fixing_session",
                    metadata={
                        "session_id": self.session_id,
                        "total_notebooks": len(failed_notebooks),
                        "max_attempts_per_notebook": self.max_attempts,
                        "notebook_paths": [
                            nb.notebook_path for nb in failed_notebooks[:5]
                        ],  # First 5 for brevity
                    },
                )
            except Exception as e:
                print(f"⚠️  LangFuse session span creation failed: {e}")

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
            original_notebook_path="",
        )

        # Execute the contextual workflow with recursion limit configuration
        config = {"recursion_limit": 100}

        try:
            final_state = await self.graph.ainvoke(initial_state, config)

            # Update LangFuse with final results
            if session_span:
                try:
                    self.langfuse.update_current_span(
                        output={
                            "success_count": final_state["success_count"],
                            "failure_count": final_state["failure_count"],
                            "total_attempts": final_state["total_attempts"],
                            "success_rate": final_state["success_count"]
                            / len(failed_notebooks)
                            if failed_notebooks
                            else 0,
                            "average_attempts": final_state["total_attempts"]
                            / len(failed_notebooks)
                            if failed_notebooks
                            else 0,
                            "strategy_effectiveness": final_state[
                                "strategy_effectiveness"
                            ],
                            "accumulated_knowledge_length": len(
                                final_state["accumulated_knowledge"]
                            ),
                        }
                    )
                except Exception as e:
                    print(f"⚠️  LangFuse session span update failed: {e}")

        except Exception as e:
            # Log error to LangFuse
            if session_span:
                try:
                    self.langfuse.update_current_span(
                        output={"error": str(e), "success": False}
                    )
                except Exception as e2:
                    print(f"⚠️  LangFuse error logging failed: {e2}")
            raise

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
