#!/usr/bin/env python3
"""
MCP-Based Notebook Fixer using Devstral and Jupyter MCP Server

This architecture uses:
1. MCP Client for Ollama (ollmcp) to connect Devstral with MCP servers
2. Jupyter MCP Server to provide notebook manipulation tools
3. Custom test runner integration

The AI can directly edit notebook cells, run code, and fix issues through MCP tools.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any
import signal
import atexit
import shutil

# Vector database and embeddings imports
try:
    from langchain_ollama import OllamaEmbeddings
    from langchain_chroma import Chroma
    from langchain.schema import Document
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    import re

    VECTOR_DB_AVAILABLE = True
    print("📊 Vector database capabilities available")
except ImportError:
    VECTOR_DB_AVAILABLE = False
    print(
        "⚠️  Vector database not available. Install with: pip install langchain-ollama langchain-chroma"
    )


@dataclass
class NotebookFailure:
    """Represents a notebook test failure."""

    notebook_path: str
    classname: str
    test_name: str
    failure_type: str
    original_failure_message: str
    original_error_output: str
    execution_time: float


@dataclass
class VectorContext:
    """Contains vector database context for enhanced fixing."""

    similar_examples: List[Document] = field(default_factory=list)
    error_patterns: List[Document] = field(default_factory=list)
    api_documentation: List[Document] = field(default_factory=list)
    context_summary: str = ""


@dataclass
class MCPSession:
    """Manages an MCP session for notebook fixing."""

    jupyter_process: Optional[subprocess.Popen] = None
    jupyter_port: int = 8888
    jupyter_token: str = "MY_TOKEN"
    mcp_config_file: Optional[str] = None
    ollmcp_process: Optional[subprocess.Popen] = None


class MCPNotebookFixer:
    """Notebook fixer using MCP architecture with tool-enabled models, Jupyter MCP Server, and vector database integration."""

    def __init__(
        self,
        model_name: str = "devstral",
        jupyter_port: int = 8888,
        vectordb_path: str = "./atoti_docs_vectordb",
    ):
        """Initialize the MCP-based notebook fixer with vector database support."""
        self.model_name = model_name
        self.jupyter_port = jupyter_port
        self.jupyter_token = "MY_TOKEN"
        self.vectordb_path = vectordb_path

        # Initialize vector database components
        self.embeddings = None
        self.vectordb = None
        self.knowledge_base_ready = False

        if VECTOR_DB_AVAILABLE:
            self._setup_vector_database()

        self.session = MCPSession(
            jupyter_port=jupyter_port, jupyter_token=self.jupyter_token
        )

        # Register cleanup on exit
        atexit.register(self.cleanup)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        print(f"\n🛑 Received signal {signum}, cleaning up...")
        self.cleanup()
        sys.exit(0)

    def _setup_vector_database(self):
        """Initialize vector database connection to existing persisted database."""
        if not VECTOR_DB_AVAILABLE:
            return False

        try:
            print("📊 Setting up vector database connection...")

            # Initialize embeddings (same as agents.py - use mxbai-embed-large for 1024 dimensions)
            self.embeddings = OllamaEmbeddings(
                model="mxbai-embed-large",
            )

            # Connect to existing persisted vector database
            if os.path.exists(self.vectordb_path):
                # Connect to the default collection name (langchain) where documents are stored
                self.vectordb = Chroma(
                    persist_directory=self.vectordb_path,
                    embedding_function=self.embeddings,
                    # Don't specify collection_name to use default "langchain" collection
                )
                self.knowledge_base_ready = True
                print(
                    f"✅ Connected to existing vector database at {self.vectordb_path}"
                )

                # Check collection size
                collection_size = self.vectordb._collection.count()
                collection_name = self.vectordb._collection.name
                print(
                    f"📚 Knowledge base collection '{collection_name}' contains {collection_size} documents"
                )
                return True
            else:
                print(f"⚠️  Vector database not found at {self.vectordb_path}")
                print("   Run agents.py to create the knowledge base first")
                self.knowledge_base_ready = False
                return False

        except Exception as e:
            print(f"❌ Error setting up vector database: {e}")
            self.knowledge_base_ready = False
            return False

    def _validate_vector_database(self) -> bool:
        """Validate vector database availability before starting MCP session."""
        print("📊 Validating vector database...")

        if not VECTOR_DB_AVAILABLE:
            print("⚠️  Vector database dependencies not available")
            print("   Install with: pip install langchain-ollama langchain-chroma")
            return False

        if not os.path.exists(self.vectordb_path):
            print(f"⚠️  Vector database not found at {self.vectordb_path}")
            print("   Run 'python tests/utils/agents.py' to create the knowledge base")
            return False

        # Try to connect and validate
        try:
            if not self.knowledge_base_ready:
                print("🔄 Attempting to reconnect to vector database...")
                if not self._setup_vector_database():
                    return False

            # Test the connection
            collection_size = self.vectordb._collection.count()
            if collection_size == 0:
                print("⚠️  Vector database is empty")
                print(
                    "   Run 'python tests/utils/agents.py' to populate the knowledge base"
                )
                return False

            print(f"✅ Vector database validated: {collection_size} documents ready")
            return True

        except Exception as e:
            print(f"❌ Vector database validation failed: {e}")
            self.knowledge_base_ready = False
            return False

    def _get_vector_context(
        self, notebook_path: str, failures: List[NotebookFailure]
    ) -> VectorContext:
        """Retrieve relevant context from vector database for enhanced fixing."""
        if not self.knowledge_base_ready:
            return VectorContext()

        try:
            # Create search queries from failures
            error_queries = []
            for failure in failures:
                error_queries.extend(
                    [
                        failure.failure_type,
                        failure.original_failure_message[:200],
                        f"notebook error {failure.failure_type}",
                    ]
                )

            # Add notebook path context
            notebook_name = Path(notebook_path).stem
            error_queries.append(f"atoti {notebook_name}")

            # Search for relevant context
            context = VectorContext()

            for query in error_queries[:5]:  # Limit queries to avoid overload
                if query.strip():
                    try:
                        results = self.vectordb.similarity_search(
                            query,
                            k=3,  # Get top 3 results per query
                        )

                        # Categorize results
                        for doc in results:
                            if "error" in doc.metadata.get("type", "").lower():
                                context.error_patterns.append(doc)
                            elif "example" in doc.metadata.get("type", "").lower():
                                context.similar_examples.append(doc)
                            else:
                                context.api_documentation.append(doc)

                    except Exception as e:
                        print(f"⚠️  Error searching vector DB for '{query}': {e}")
                        continue

            # Remove duplicates and limit results
            context.similar_examples = list(
                {doc.page_content: doc for doc in context.similar_examples}.values()
            )[:5]
            context.error_patterns = list(
                {doc.page_content: doc for doc in context.error_patterns}.values()
            )[:5]
            context.api_documentation = list(
                {doc.page_content: doc for doc in context.api_documentation}.values()
            )[:10]

            # Create context summary
            total_docs = (
                len(context.similar_examples)
                + len(context.error_patterns)
                + len(context.api_documentation)
            )
            context.context_summary = (
                f"Retrieved {total_docs} relevant documents from knowledge base"
            )

            print(
                f"🔍 Vector context: {len(context.similar_examples)} examples, {len(context.error_patterns)} error patterns, {len(context.api_documentation)} API docs"
            )

            return context

        except Exception as e:
            print(f"❌ Error retrieving vector context: {e}")
            return VectorContext()

    def setup_jupyter_server(self, notebook_dir: str = None) -> bool:
        """Start JupyterLab server for MCP integration."""
        if notebook_dir is None:
            notebook_dir = os.getcwd()

        print(f"🚀 Starting JupyterLab server on port {self.jupyter_port}...")

        # Check if JupyterLab is already running
        if self._is_jupyter_running():
            print(f"✅ JupyterLab already running on port {self.jupyter_port}")
            return True

        try:
            # Start JupyterLab with required configuration
            cmd = [
                sys.executable,
                "-m",
                "jupyterlab",
                "--port",
                str(self.jupyter_port),
                "--IdentityProvider.token",
                self.jupyter_token,
                "--ip",
                "0.0.0.0",
                "--no-browser",
                "--allow-root",
                f"--notebook-dir={notebook_dir}",
            ]

            self.session.jupyter_process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )

            # Wait for server to start
            for i in range(30):  # Wait up to 30 seconds
                if self._is_jupyter_running():
                    print(
                        f"✅ JupyterLab started successfully on port {self.jupyter_port}"
                    )
                    return True
                time.sleep(1)

            print("❌ JupyterLab failed to start within 30 seconds")
            return False

        except Exception as e:
            print(f"❌ Error starting JupyterLab: {e}")
            return False

    def _is_jupyter_running(self) -> bool:
        """Check if JupyterLab is running on the specified port."""
        try:
            import urllib.request
            import urllib.parse

            url = f"http://localhost:{self.jupyter_port}/api/status"
            params = urllib.parse.urlencode({"token": self.jupyter_token})
            full_url = f"{url}?{params}"

            response = urllib.request.urlopen(full_url, timeout=2)
            return response.status == 200
        except:
            return False

    def create_mcp_config(self, notebook_path: str) -> str:
        """Create MCP configuration file for the Jupyter server."""
        config = {
            "mcpServers": {
                "jupyter": {
                    "command": "docker",
                    "args": [
                        "run",
                        "-i",
                        "--rm",
                        "-e",
                        "ROOM_URL",
                        "-e",
                        "ROOM_TOKEN",
                        "-e",
                        "ROOM_ID",
                        "-e",
                        "RUNTIME_URL",
                        "-e",
                        "RUNTIME_TOKEN",
                        "--network=host" if sys.platform.startswith("linux") else None,
                        "datalayer/jupyter-mcp-server:latest",
                    ],
                    "env": {
                        "ROOM_URL": f"http://{'localhost' if sys.platform.startswith('linux') else 'host.docker.internal'}:{self.jupyter_port}",
                        "ROOM_TOKEN": self.jupyter_token,
                        "ROOM_ID": notebook_path,
                        "RUNTIME_URL": f"http://{'localhost' if sys.platform.startswith('linux') else 'host.docker.internal'}:{self.jupyter_port}",
                        "RUNTIME_TOKEN": self.jupyter_token,
                    },
                }
            }
        }

        # Remove None values from args
        config["mcpServers"]["jupyter"]["args"] = [
            arg for arg in config["mcpServers"]["jupyter"]["args"] if arg is not None
        ]

        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config, f, indent=2)
            self.session.mcp_config_file = f.name
            print(f"📝 Created MCP config: {f.name}")
            return f.name

    def ensure_docker_image(self) -> bool:
        """Ensure the Jupyter MCP Server Docker image is available."""
        print("🐳 Checking for Jupyter MCP Server Docker image...")

        try:
            # Check if image exists
            result = subprocess.run(
                [
                    "docker",
                    "images",
                    "datalayer/jupyter-mcp-server:latest",
                    "--format",
                    "{{.Repository}}",
                ],
                capture_output=True,
                text=True,
            )

            if "datalayer/jupyter-mcp-server" in result.stdout:
                print("✅ Jupyter MCP Server image found")
                return True

            # Pull the image
            print("📥 Pulling Jupyter MCP Server image...")
            result = subprocess.run(
                ["docker", "pull", "datalayer/jupyter-mcp-server:latest"],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                print("✅ Jupyter MCP Server image pulled successfully")
                return True
            else:
                print(f"❌ Failed to pull image: {result.stderr}")
                return False

        except Exception as e:
            print(f"❌ Docker error: {e}")
            return False

    def install_ollmcp(self) -> bool:
        """Install the MCP client for Ollama if not already installed."""
        try:
            # Check if ollmcp is installed
            result = subprocess.run(
                ["ollmcp", "--version"], capture_output=True, text=True
            )
            if result.returncode == 0:
                print("✅ ollmcp already installed")
                return True
        except FileNotFoundError:
            pass

        print("📦 Installing ollmcp...")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "ollmcp"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                print("✅ ollmcp installed successfully")
                return True
            else:
                print(f"❌ Failed to install ollmcp: {result.stderr}")
                return False
        except Exception as e:
            print(f"❌ Error installing ollmcp: {e}")
            return False

    def fix_notebook(
        self, notebook_path: str, failures: List[NotebookFailure]
    ) -> Dict[str, Any]:
        """
        Fix a notebook using MCP architecture with vector database context.

        This method:
        1. Validates vector database availability
        2. Ensures prerequisites are met
        3. Sets up JupyterLab server
        4. Retrieves relevant context from vector database
        5. Creates MCP configuration for the notebook
        6. Launches ollmcp with Devstral and enhanced context to fix the issues
        7. Validates the fixes
        """
        print(f"\n🔧 Starting MCP-based fix for: {notebook_path}")

        # STEP 1: Validate vector database BEFORE starting MCP session
        vector_db_available = self._validate_vector_database()

        if vector_db_available and self.knowledge_base_ready:
            print("📚 Vector database ready - will provide enhanced context")
        else:
            print("⚠️  Vector database not available - using basic context only")
            # Continue without vector database - not a blocking error

        # STEP 2: Ensure MCP prerequisites are met
        if not self.install_ollmcp():
            return {"success": False, "error": "Failed to install ollmcp"}

        if not self.ensure_docker_image():
            return {"success": False, "error": "Failed to ensure Docker image"}

        # STEP 3: Setup JupyterLab server
        notebook_dir = str(Path(notebook_path).parent)
        if not self.setup_jupyter_server(notebook_dir):
            return {"success": False, "error": "Failed to start JupyterLab server"}

        # Create MCP configuration
        relative_notebook_path = str(Path(notebook_path).relative_to(notebook_dir))
        config_file = self.create_mcp_config(relative_notebook_path)

        # Create fixing prompt with error context and vector database enhancement
        fixing_prompt = self._create_fixing_prompt(notebook_path, failures)

        try:
            # Run ollmcp with the enhanced fixing prompt
            print("🤖 Launching AI model with MCP tools and enhanced context...")
            success = self._run_interactive_fixing_session(config_file, fixing_prompt)

            if success:
                # Validate the fix
                return self._validate_notebook_fix(notebook_path)
            else:
                return {"success": False, "error": "Interactive fixing session failed"}

        except Exception as e:
            return {"success": False, "error": f"Fixing process failed: {str(e)}"}

        finally:
            # Cleanup will be handled by atexit/signal handlers
            pass

    def _create_fixing_prompt(
        self, notebook_path: str, failures: List[NotebookFailure]
    ) -> str:
        """Create a comprehensive prompt for fixing the notebook with vector database context."""

        # Get vector database context if available
        vector_context = self._get_vector_context(notebook_path, failures)

        prompt_lines = [
            "🔧 NOTEBOOK FIXING TASK WITH ENHANCED CONTEXT",
            "=" * 60,
            "",
            f"Notebook: {notebook_path}",
            f"Failures to fix: {len(failures)}",
            "",
        ]

        # Add vector database context if available
        if vector_context.context_summary:
            prompt_lines.extend(
                [
                    "📚 KNOWLEDGE BASE CONTEXT:",
                    f"   {vector_context.context_summary}",
                    "",
                ]
            )

            # Add relevant examples
            if vector_context.similar_examples:
                prompt_lines.extend(
                    [
                        "🔍 RELEVANT CODE EXAMPLES:",
                    ]
                )
                for i, doc in enumerate(vector_context.similar_examples[:3], 1):
                    source = doc.metadata.get("source", "Unknown")
                    content = (
                        doc.page_content[:300] + "..."
                        if len(doc.page_content) > 300
                        else doc.page_content
                    )
                    prompt_lines.extend(
                        [
                            f"   Example {i} (from {source}):",
                            f"   {content}",
                            "",
                        ]
                    )

            # Add error patterns
            if vector_context.error_patterns:
                prompt_lines.extend(
                    [
                        "⚠️ KNOWN ERROR PATTERNS & SOLUTIONS:",
                    ]
                )
                for i, doc in enumerate(vector_context.error_patterns[:2], 1):
                    source = doc.metadata.get("source", "Unknown")
                    content = (
                        doc.page_content[:300] + "..."
                        if len(doc.page_content) > 300
                        else doc.page_content
                    )
                    prompt_lines.extend(
                        [
                            f"   Pattern {i} (from {source}):",
                            f"   {content}",
                            "",
                        ]
                    )

            # Add API documentation
            if vector_context.api_documentation:
                prompt_lines.extend(
                    [
                        "📖 RELEVANT API DOCUMENTATION:",
                    ]
                )
                for i, doc in enumerate(vector_context.api_documentation[:2], 1):
                    source = doc.metadata.get("source", "Unknown")
                    content = (
                        doc.page_content[:300] + "..."
                        if len(doc.page_content) > 300
                        else doc.page_content
                    )
                    prompt_lines.extend(
                        [
                            f"   API Doc {i} (from {source}):",
                            f"   {content}",
                            "",
                        ]
                    )

        prompt_lines.extend(
            [
                "🚨 FAILURE DETAILS:",
            ]
        )

        for i, failure in enumerate(failures, 1):
            prompt_lines.extend(
                [
                    f"{i}. {failure.test_name}",
                    f"   Type: {failure.failure_type}",
                    f"   Message: {failure.original_failure_message}",
                    f"   Output: {failure.original_error_output[:500]}...",
                    "",
                ]
            )

        prompt_lines.extend(
            [
                "📋 ENHANCED FIXING INSTRUCTIONS:",
                "1. Use get_notebook_info to examine the notebook structure",
                "2. Use read_cell to examine problematic cells",
                "3. LEVERAGE the provided context examples and patterns above",
                "4. Apply similar solutions from the knowledge base context",
                "5. Use insert_execute_code_cell or modify existing cells to fix issues",
                "6. Test your fixes by executing cells",
                "7. Verify the notebook runs without errors",
                "",
                "🎯 PRIORITY FOCUS AREAS:",
                "- Import errors and missing dependencies (check context examples)",
                "- Syntax errors and typos (reference error patterns)",
                "- Path and file reference issues",
                "- Data loading and processing errors",
                "- API compatibility issues (use API documentation context)",
                "- Atoti-specific patterns and best practices",
                "",
                "💡 CONTEXT-AWARE STRATEGY:",
                "- Study the provided examples before making changes",
                "- Apply similar patterns from the knowledge base",
                "- Use the error patterns to avoid common mistakes",
                "- Reference the API documentation for correct usage",
                "",
                "🚀 START: Use the Jupyter MCP tools to examine and fix the notebook.",
                "Begin by examining the notebook structure with get_notebook_info.",
            ]
        )

        return "\n".join(prompt_lines)

    def _run_interactive_fixing_session(self, config_file: str, prompt: str) -> bool:
        """Run an interactive ollmcp session for fixing."""
        try:
            # Create a script to run ollmcp with the prompt
            script_content = f'''#!/bin/bash
echo "Starting MCP notebook fixing session..."
echo "Config file: {config_file}"
echo "Model: {self.model_name}"

# Send the initial prompt to ollmcp
echo "{prompt}" | ollmcp --servers-json {config_file} --model {self.model_name}
'''

            with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
                f.write(script_content)
                script_path = f.name

            os.chmod(script_path, 0o755)

            print(f"📋 Running fixing session with prompt:")
            print(prompt[:200] + "..." if len(prompt) > 200 else prompt)
            print("\n🚀 Launching interactive MCP session...")
            print("💡 Use the Jupyter MCP tools to examine and fix the notebook")
            print("💡 Type 'quit' when done fixing")

            # Run the interactive session
            result = subprocess.run([script_path], shell=True)

            os.unlink(script_path)
            return result.returncode == 0

        except Exception as e:
            print(f"❌ Error running interactive session: {e}")
            return False

    def _validate_notebook_fix(self, notebook_path: str) -> Dict[str, Any]:
        """Validate that the notebook has been fixed."""
        print("🧪 Validating notebook fixes...")

        try:
            # Run the notebook test
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/01_test_notebooks.py::test_notebook",
                    f"[{notebook_path}]",
                    "-v",
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )

            success = result.returncode == 0

            return {
                "success": success,
                "notebook_path": notebook_path,
                "test_output": result.stdout + result.stderr,
                "message": "✅ Notebook fixed successfully!"
                if success
                else "❌ Notebook still has issues",
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "notebook_path": notebook_path,
                "test_output": "",
                "message": "❌ Test validation timed out",
            }
        except Exception as e:
            return {
                "success": False,
                "notebook_path": notebook_path,
                "test_output": "",
                "message": f"❌ Validation error: {str(e)}",
            }

    def cleanup(self):
        """Clean up resources."""
        print("\n🧹 Cleaning up MCP session...")

        # Stop ollmcp process
        if self.session.ollmcp_process:
            try:
                self.session.ollmcp_process.terminate()
                self.session.ollmcp_process.wait(timeout=5)
            except:
                try:
                    self.session.ollmcp_process.kill()
                except:
                    pass

        # Stop JupyterLab process
        if self.session.jupyter_process:
            try:
                self.session.jupyter_process.terminate()
                self.session.jupyter_process.wait(timeout=5)
                print("✅ JupyterLab stopped")
            except:
                try:
                    self.session.jupyter_process.kill()
                except:
                    pass

        # Remove config file
        if self.session.mcp_config_file and os.path.exists(
            self.session.mcp_config_file
        ):
            try:
                os.unlink(self.session.mcp_config_file)
                print("✅ Config file cleaned up")
            except:
                pass

    @staticmethod
    def parse_junit_xml(xml_file_path: str) -> List[NotebookFailure]:
        """Parse JUnit XML to extract notebook failures."""
        failures = []

        try:
            tree = ET.parse(xml_file_path)
            root = tree.getroot()

            for testcase in root.findall(".//testcase"):
                classname = testcase.get("classname", "")
                name = testcase.get("name", "")
                time = float(testcase.get("time", 0))

                # Look for failures or errors
                failure_elem = testcase.find("failure")
                error_elem = testcase.find("error")

                if failure_elem is not None or error_elem is not None:
                    elem = failure_elem if failure_elem is not None else error_elem
                    failure_type = elem.get("type", "unknown")
                    message = elem.get("message", "")
                    text = elem.text or ""

                    # Extract notebook path from test name
                    notebook_path = MCPNotebookFixer._extract_notebook_path(
                        name, classname
                    )

                    if notebook_path:
                        failure = NotebookFailure(
                            notebook_path=notebook_path,
                            classname=classname,
                            test_name=name,
                            failure_type=failure_type,
                            original_failure_message=message,
                            original_error_output=text,
                            execution_time=time,
                        )
                        failures.append(failure)

        except Exception as e:
            print(f"Error parsing JUnit XML: {e}")

        return failures

    @staticmethod
    def _extract_notebook_path(test_name: str, classname: str) -> str:
        """Extract notebook path from test name."""
        # Handle test_notebook[path] format
        if "[" in test_name and "]" in test_name:
            start = test_name.find("[") + 1
            end = test_name.find("]")
            return test_name[start:end]

        # Fallback - construct from classname
        if "test_notebooks" in classname:
            return test_name.replace("test_", "").replace("_", "/")

        return test_name


def main():
    """Command-line interface for the MCP notebook fixer."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Fix notebooks using MCP architecture with Devstral and vector database context"
    )
    parser.add_argument("input", help="JUnit XML file with failures or notebook path")
    parser.add_argument("--model", "-m", default="devstral", help="Ollama model to use")
    parser.add_argument("--port", "-p", type=int, default=8888, help="JupyterLab port")
    parser.add_argument(
        "--notebook", "-n", help="Single notebook to fix (if not using XML)"
    )
    parser.add_argument(
        "--vectordb",
        "-v",
        default="./atoti_docs_vectordb",
        help="Path to vector database (default: ./atoti_docs_vectordb)",
    )

    args = parser.parse_args()

    fixer = MCPNotebookFixer(
        model_name=args.model, jupyter_port=args.port, vectordb_path=args.vectordb
    )

    try:
        if args.notebook:
            # Fix a single notebook
            dummy_failure = NotebookFailure(
                notebook_path=args.notebook,
                classname="TestNotebook",
                test_name="test_notebook",
                failure_type="execution_error",
                original_failure_message="Notebook execution failed",
                original_error_output="",
                execution_time=0.0,
            )

            result = fixer.fix_notebook(args.notebook, [dummy_failure])
            print(f"\n{'=' * 60}")
            print("FIXING RESULT:")
            for key, value in result.items():
                print(f"{key}: {value}")

        else:
            # Parse failures from XML and fix them
            if not os.path.exists(args.input):
                print(f"Error: File {args.input} does not exist")
                sys.exit(1)

            failures = fixer.parse_junit_xml(args.input)
            if not failures:
                print("No failures found in XML file")
                return

            print(f"📋 Found {len(failures)} failures to fix")

            # Group failures by notebook
            notebook_failures = {}
            for failure in failures:
                notebook_path = failure.notebook_path
                if notebook_path not in notebook_failures:
                    notebook_failures[notebook_path] = []
                notebook_failures[notebook_path].append(failure)

            # Process each notebook
            results = []
            for notebook_path, nb_failures in notebook_failures.items():
                print(f"\n{'=' * 60}")
                print(f"Processing: {notebook_path}")
                print(f"Failures: {len(nb_failures)}")

                result = fixer.fix_notebook(notebook_path, nb_failures)
                results.append(result)

                if result["success"]:
                    print(f"✅ {notebook_path} - FIXED")
                else:
                    print(
                        f"❌ {notebook_path} - FAILED: {result.get('error', 'Unknown error')}"
                    )

            # Summary
            successful = len([r for r in results if r.get("success", False)])
            total = len(results)
            print(f"\n{'=' * 60}")
            print("FINAL SUMMARY:")
            print(f"Total notebooks: {total}")
            print(f"Successful fixes: {successful}")
            print(f"Failed fixes: {total - successful}")
            print(
                f"Success rate: {(successful / total) * 100:.1f}%"
                if total > 0
                else "0%"
            )

    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
    except Exception as e:
        print(f"\n💥 Error: {e}")
    finally:
        fixer.cleanup()


if __name__ == "__main__":
    main()
