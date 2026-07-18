import os
import subprocess
import tensorflow as tf # Not needed, just checking import
import sys

def main():
    proto_dir = "proto"
    out_dir = "core/proto"
    
    os.makedirs(out_dir, exist_ok=True)
    
    # Run the protobuf compiler compiler
    cmd = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"-I{proto_dir}",
        f"--python_out={out_dir}",
        f"--grpc_python_out={out_dir}",
        os.path.join(proto_dir, "trilith.proto")
    ]
    print(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("Compilation failed:")
        print(result.stderr)
        sys.exit(1)
        
    print("Compilation successful.")
    
    # Patch imports in trilith_pb2_grpc.py
    grpc_path = os.path.join(out_dir, "trilith_pb2_grpc.py")
    if os.path.exists(grpc_path):
        with open(grpc_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Target import statement
        target = "import trilith_pb2 as trilith__pb2"
        replacement = "from . import trilith_pb2 as trilith__pb2"
        
        if target in content:
            content = content.replace(target, replacement)
            with open(grpc_path, "w", encoding="utf-8") as f:
                f.write(content)
            print("Successfully patched absolute import to relative import in trilith_pb2_grpc.py.")
        else:
            print("Import statement standard replacement not found (already relative or different?).")

if __name__ == "__main__":
    main()
