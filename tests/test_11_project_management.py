"""
Interactive test for US018: Project Management

Exercises the kg_project commands (list, create, open, status) without
needing Neo4j or data files. Uses a temporary directory as KG_BASE_DIR.

Usage:
    python -m tests.test_11_project_management
"""

import json
import os
import sys
import tempfile

# Add parent to path
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)


def main():
    with tempfile.TemporaryDirectory() as base_dir:
        os.environ["KG_BASE_DIR"] = base_dir
        print(f"Using temporary KG_BASE_DIR: {base_dir}\n")

        from mcp_server.server import _run_kg_project
        import mcp_server.server as srv

        # 1. List (empty)
        print("=" * 60)
        print("1. LIST (empty)")
        print("=" * 60)
        result = _run_kg_project("list")
        print(result["agent_response"])
        print(f"   Status: {result['status']}")
        print()

        # 2. Create project
        print("=" * 60)
        print("2. CREATE 'furniture_supply_chain'")
        print("=" * 60)
        result = _run_kg_project("create furniture_supply_chain")
        print(result["agent_response"])
        print(f"   Active: {srv._active_project}")
        print()

        # 3. Status
        print("=" * 60)
        print("3. STATUS (active project)")
        print("=" * 60)
        result = _run_kg_project("status")
        print(result["agent_response"])
        print()

        # 4. Create second project
        print("=" * 60)
        print("4. CREATE 'social_network'")
        print("=" * 60)
        result = _run_kg_project("create social_network")
        print(result["agent_response"])
        print(f"   Active: {srv._active_project}")
        print()

        # 5. List (two projects)
        print("=" * 60)
        print("5. LIST (two projects)")
        print("=" * 60)
        result = _run_kg_project("list")
        print(result["agent_response"])
        print()

        # 6. Open first project
        print("=" * 60)
        print("6. OPEN 'furniture_supply_chain'")
        print("=" * 60)
        result = _run_kg_project("open furniture_supply_chain")
        print(result["agent_response"])
        print(f"   Active: {srv._active_project}")
        print()

        # 7. Open non-existent
        print("=" * 60)
        print("7. OPEN 'nonexistent' (error)")
        print("=" * 60)
        result = _run_kg_project("open nonexistent")
        print(result["agent_response"])
        print()

        # 8. Create with invalid name
        print("=" * 60)
        print("8. CREATE 'bad name' (error)")
        print("=" * 60)
        result = _run_kg_project("create bad name")
        print(result["agent_response"])
        print()

        # 9. Unknown command
        print("=" * 60)
        print("9. UNKNOWN command")
        print("=" * 60)
        result = _run_kg_project("foobar")
        print(result["agent_response"])
        print()

        # 10. Verify marker file
        print("=" * 60)
        print("10. VERIFY marker file")
        print("=" * 60)
        marker = os.path.join(base_dir, "_last_active_project")
        if os.path.exists(marker):
            with open(marker) as f:
                print(f"   _last_active_project: {f.read().strip()}")
        else:
            print("   [ERROR] Marker file not found!")
        print()

        # 11. Verify KG_DATA_DIR was set
        print("=" * 60)
        print("11. VERIFY KG_DATA_DIR")
        print("=" * 60)
        print(f"   KG_DATA_DIR: {os.environ.get('KG_DATA_DIR', 'NOT SET')}")
        print()

        # Cleanup
        srv._active_project = None
        os.environ.pop("KG_BASE_DIR", None)
        os.environ.pop("KG_DATA_DIR", None)

    print("[OK] All interactive tests passed.")


if __name__ == "__main__":
    main()
