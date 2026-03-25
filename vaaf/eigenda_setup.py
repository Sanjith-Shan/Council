"""
EigenDA Proto Setup
-------------------
Downloads EigenDA proto files from GitHub and compiles Python stubs.
Run once: python vaaf/eigenda_setup.py
"""

import os
import sys
import subprocess
import urllib.request
from pathlib import Path


PROTOS = {
    "disperser/disperser.proto": "https://raw.githubusercontent.com/Layr-Labs/eigenda/master/api/proto/disperser/v2/disperser_v2.proto",
    "common/common.proto": "https://raw.githubusercontent.com/Layr-Labs/eigenda/master/api/proto/common/v2/common_v2.proto",
}

# Fallback to v1 protos if v2 not available
PROTOS_V1 = {
    "disperser/disperser.proto": "https://raw.githubusercontent.com/Layr-Labs/eigenda/master/api/proto/disperser/disperser.proto",
    "common/common.proto": "https://raw.githubusercontent.com/Layr-Labs/eigenda/master/api/proto/common/common.proto",
}


def main():
    project_root = Path(__file__).parent.parent
    proto_dir = project_root / "proto"
    output_dir = project_root / "vaaf" / "proto"

    # Install grpc tools
    print("Installing gRPC tools...")
    subprocess.run([sys.executable, "-m", "pip", "install", "grpcio", "grpcio-tools", "protobuf"],
                   capture_output=True)

    # Create directories
    (proto_dir / "disperser").mkdir(parents=True, exist_ok=True)
    (proto_dir / "common").mkdir(parents=True, exist_ok=True)
    (output_dir / "disperser").mkdir(parents=True, exist_ok=True)
    (output_dir / "common").mkdir(parents=True, exist_ok=True)

    # Download proto files (try v1 first since it's more stable)
    print("Downloading EigenDA proto files...")
    for rel_path, url in PROTOS_V1.items():
        dest = proto_dir / rel_path
        try:
            print(f"  Downloading {rel_path}...")
            urllib.request.urlretrieve(url, dest)
            print(f"  ✓ {rel_path}")
        except Exception as e:
            print(f"  ✗ Failed to download {rel_path}: {e}")
            # Try v2
            v2_url = PROTOS.get(rel_path)
            if v2_url:
                try:
                    urllib.request.urlretrieve(v2_url, dest)
                    print(f"  ✓ {rel_path} (v2)")
                except Exception as e2:
                    print(f"  ✗ Also failed v2: {e2}")
                    return False

    # Create __init__.py files
    (output_dir / "__init__.py").touch()
    (output_dir / "disperser" / "__init__.py").touch()
    (output_dir / "common" / "__init__.py").touch()

    # Compile proto files
    print("Compiling proto files...")
    try:
        result = subprocess.run([
            sys.executable, "-m", "grpc_tools.protoc",
            f"--proto_path={proto_dir}",
            f"--python_out={output_dir}",
            f"--grpc_python_out={output_dir}",
            str(proto_dir / "disperser" / "disperser.proto"),
            str(proto_dir / "common" / "common.proto"),
        ], capture_output=True, text=True)

        if result.returncode != 0:
            print(f"Proto compilation failed: {result.stderr}")
            # Try without common proto
            result2 = subprocess.run([
                sys.executable, "-m", "grpc_tools.protoc",
                f"--proto_path={proto_dir}",
                f"--python_out={output_dir}",
                f"--grpc_python_out={output_dir}",
                str(proto_dir / "disperser" / "disperser.proto"),
            ], capture_output=True, text=True)
            if result2.returncode != 0:
                print(f"Still failed: {result2.stderr}")
                return False

        print("✓ Proto compilation successful")

        # Fix imports in generated files
        for py_file in output_dir.rglob("*.py"):
            content = py_file.read_text()
            if "from disperser" in content or "from common" in content:
                content = content.replace("from disperser", "from vaaf.proto.disperser")
                content = content.replace("from common", "from vaaf.proto.common")
                py_file.write_text(content)
                print(f"  Fixed imports in {py_file.name}")

    except Exception as e:
        print(f"Compilation error: {e}")
        return False

    # Verify
    print("\nVerifying...")
    try:
        # Add project root to path for import
        sys.path.insert(0, str(project_root))
        from vaaf.proto.disperser import disperser_pb2, disperser_pb2_grpc
        print("✓ Proto stubs import successfully")
        print(f"\n✓ EigenDA setup complete!")
        print(f"  Proto files: {proto_dir}")
        print(f"  Python stubs: {output_dir}")
        print(f"  Test: python -c \"from vaaf.eigenda_client import EigenDAClient; print(EigenDAClient().is_available)\"")
        return True
    except ImportError as e:
        print(f"✗ Import verification failed: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
