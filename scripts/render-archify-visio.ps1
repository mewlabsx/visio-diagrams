param(
 [Parameter(Mandatory)][string]$SpecPath,
 [Parameter(Mandatory)][string]$OutputPath,
 [string]$ArchifyRoot=(Join-Path $env:USERPROFILE '.agents\skills\archify'),
 [ValidateSet('spec','on','off')][string]$ColorFill='spec',
 [ValidateSet('python','com')][string]$Backend='python',
 [string]$StencilPath
)
$ErrorActionPreference='Stop'
$out=[IO.Path]::GetFullPath($OutputPath)
$layout=[IO.Path]::ChangeExtension($out,'.layout.json')
$native=[IO.Path]::ChangeExtension($out,'.native.json')
$quality=[IO.Path]::ChangeExtension($out,'.archify-validation.json')
foreach($path in @($out,$layout,$native,$quality,[IO.Path]::ChangeExtension($out,'.png'),[IO.Path]::ChangeExtension($out,'.validation.json'))){if(Test-Path -LiteralPath $path){throw "Refusing to overwrite: $path"}}
$cli=Join-Path $ArchifyRoot 'bin\archify.mjs'
if(-not (Test-Path -LiteralPath $cli)){throw 'Installed Archify not found; use -ArchifyRoot'}
[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($out)) | Out-Null
$result=& node $cli validate workflow $SpecPath --layout-json
if($LASTEXITCODE -ne 0){throw 'Archify layout did not pass'}
$result | Set-Content -LiteralPath $layout -Encoding utf8
$result=& node $cli validate workflow $SpecPath --quality showcase --json
$result | Set-Content -LiteralPath $quality -Encoding utf8
if($LASTEXITCODE -ne 0){throw 'Archify quality validation failed'}
$receipt=$result -join "`n" | ConvertFrom-Json
if(-not $receipt.ok -or $receipt.composition.summary.errors -ne 0 -or $receipt.composition.summary.warnings -ne 0){throw 'Quality receipt not accepted'}
& python -X utf8 (Join-Path $PSScriptRoot 'import_archify.py') $SpecPath $layout $native
if($LASTEXITCODE -ne 0){throw 'Independent route checks or adaptation failed; native Visio not generated'}
& (Join-Path $PSScriptRoot 'render-visio.ps1') -SpecPath $native -OutputPath $out -ColorFill $ColorFill -Backend $Backend -StencilPath $StencilPath
