#!/bin/sh
# Run from a Distribution checkout outside the empty OS project.
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
bootstrap_python=
if [ "${AIVERSE_BOOTSTRAP_NO_SYSTEM_PYTHON:-0}" != 1 ]; then
    for candidate in python3.13 python3.12 python3.11 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3,11))' >/dev/null 2>&1; then
            bootstrap_python=$(command -v "$candidate")
            break
        fi
    done
fi
if [ -n "$bootstrap_python" ]; then
    exec "$bootstrap_python" -B "$script_dir/project-bootstrap.py" "$@"
fi
case "$(uname -s)/$(uname -m)" in
    Darwin/arm64) triple=aarch64-apple-darwin; digest=3663b71c18364eccfbad74c4f21f9f6149e40b07329cd776287410cc1da5d612 ;;
    Darwin/x86_64) triple=x86_64-apple-darwin; digest=4338dc0c2b954f20ca6437406db5b806626c69bae3cafeec43f1b7d57dd72a88 ;;
    Linux/aarch64) triple=aarch64-unknown-linux-gnu; digest=2238f0556d3a9777d42261b1e4d7b9834d56f111d3dd879a0647c27c824cc31d ;;
    Linux/x86_64) triple=x86_64-unknown-linux-gnu; digest=c624af93ad62a596806bbd2404e1fb80744a407ca7279854445ede16d93858b8 ;;
    *) echo 'This computer has no compatible Python and no admitted private bootstrap package.' >&2; exit 2 ;;
esac
command -v curl >/dev/null 2>&1 || { echo 'A download tool (curl) is required for initial preparation.' >&2; exit 2; }
command -v tar >/dev/null 2>&1 || { echo 'An archive tool (tar) is required for initial preparation.' >&2; exit 2; }
temporary_stack=$(mktemp -d "${TMPDIR:-/tmp}/aiverse-first-stage.XXXXXXXX")
trap 'rm -rf -- "$temporary_stack"' EXIT HUP INT TERM
archive="$temporary_stack/python.tar.gz"
url="https://github.com/astral-sh/python-build-standalone/releases/download/20261003/cpython-3.11.17%2B20261003-$triple-install_only.tar.gz"
echo 'Preparing a temporary Python interpreter outside your project…'
curl --fail --location --proto '=https' --tlsv1.2 --retry 2 --output "$archive" "$url"
if command -v sha256sum >/dev/null 2>&1; then
    actual=$(sha256sum "$archive" | cut -d ' ' -f 1)
elif command -v shasum >/dev/null 2>&1; then
    actual=$(shasum -a 256 "$archive" | cut -d ' ' -f 1)
else
    echo 'A SHA256 verification tool is required; no archive was executed.' >&2; exit 2
fi
[ "$actual" = "$digest" ] || { echo 'Python checksum verification failed; installation stopped.' >&2; exit 2; }
tar -xzf "$archive" -C "$temporary_stack"
# Do not add this temporary interpreter to PATH. The Python preparation stage
# must obtain/reuse a persistent interpreter before creating the private venv.
"$temporary_stack/python/bin/python3.11" -B "$script_dir/project-bootstrap.py" "$@"
