# Run from a Distribution checkout outside the empty OS project.
$BootstrapArguments = $args
$ErrorActionPreference = 'Stop'
$Entry = Join-Path $PSScriptRoot 'project-bootstrap.py'
if ($env:AIVERSE_BOOTSTRAP_NO_SYSTEM_PYTHON -ne '1') {
    foreach ($Name in @('python3.13', 'python3.12', 'python3.11', 'python3', 'python')) {
        $Candidate = Get-Command $Name -ErrorAction SilentlyContinue
        if ($Candidate) {
            try {
                & $Candidate.Source -c 'import sys; raise SystemExit(sys.version_info < (3,11))' 2>$null
                if ($LASTEXITCODE -eq 0) {
                    & $Candidate.Source -B $Entry @BootstrapArguments
                    exit $LASTEXITCODE
                }
            } catch { }
        }
    }
}
if ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString() -ne 'X64') {
    throw 'Windows without Python currently requires x64 for private bootstrap preparation.'
}
$TemporaryStack = Join-Path ([IO.Path]::GetTempPath()) ('aiverse-first-stage-' + [Guid]::NewGuid())
New-Item -ItemType Directory -Path $TemporaryStack | Out-Null
try {
    $Archive = Join-Path $TemporaryStack 'python.tar.gz'
    $Url = 'https://github.com/astral-sh/python-build-standalone/releases/download/20261003/cpython-3.11.17%2B20261003-x86_64-pc-windows-msvc-install_only.tar.gz'
    Write-Host 'Preparing a temporary Python interpreter outside your project…'
    Invoke-WebRequest -Uri $Url -OutFile $Archive -UseBasicParsing
    $Digest = (Get-FileHash -Algorithm SHA256 -Path $Archive).Hash.ToLowerInvariant()
    if ($Digest -ne '0f7defa7a0ed99b61e0df0bba5027474711521f1307cc3830c2f456401beeed5') {
        throw 'Python checksum verification failed; installation stopped.'
    }
    & tar -xzf $Archive -C $TemporaryStack
    if ($LASTEXITCODE -ne 0) { throw 'Python archive extraction failed.' }
    & (Join-Path $TemporaryStack 'python\python.exe') -B $Entry @BootstrapArguments
    $ExitCode = $LASTEXITCODE
} finally {
    Remove-Item -LiteralPath $TemporaryStack -Recurse -Force
}
exit $ExitCode
