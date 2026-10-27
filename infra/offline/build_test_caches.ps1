# Cache-uri offline pentru framework-urile de test ale limbajelor noi (rulează cât ai internet):
#   .NET: xUnit (șablonul `dotnet new xunit`) în %USERPROFILE%\.nuget\packages
#   Java: JUnit 5 + Surefire în %USERPROFILE%\.m2
#   R: testthat în biblioteca utilizatorului
# Go, Rust (cargo test), C/C++ (CMake + ctest) și Ruby (minitest) nu au nevoie de pachete pentru teste simple.
#   powershell -NoProfile -ExecutionPolicy Bypass -File infra/offline/build_test_caches.ps1
$ErrorActionPreference = "Continue"
$work = Join-Path $env:TEMP "petru-test-caches"
Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $work | Out-Null

function Find-Tool($name, $fallback) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    if ($fallback -and (Test-Path $fallback)) { return $fallback }
    return $null
}

$dotnet = Find-Tool "dotnet" "C:\Program Files\dotnet\dotnet.exe"
if ($dotnet) {
    & $dotnet new xunit -n PetruXunitTemplate -o "$work\PetruXunitTemplate" --force | Out-Null  # "xunit" would clash
    & $dotnet test "$work\PetruXunitTemplate" --nologo
    "dotnet: exit $LASTEXITCODE"
} else { "dotnet: missing" }

$jdk = Get-ChildItem "C:\Program Files\Eclipse Adoptium" -Directory -Filter "jdk-21*" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($jdk) { $env:JAVA_HOME = $jdk.FullName; $env:Path = "$($jdk.FullName)\bin;$env:Path" }
$mvnHome = Get-ChildItem (Join-Path $env:USERPROFILE "tools") -Directory -Filter "apache-maven-*" -ErrorAction SilentlyContinue | Select-Object -First 1
$mvn = Find-Tool "mvn" $(if ($mvnHome) { Join-Path $mvnHome.FullName "bin\mvn.cmd" })
if ($mvn) {
    $java = "$work\maven"
    New-Item -ItemType Directory -Force "$java\src\main\java\demo", "$java\src\test\java\demo" | Out-Null
    @"
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId><artifactId>demo</artifactId><version>1.0</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.junit.jupiter</groupId><artifactId>junit-jupiter</artifactId><version>5.11.4</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build><plugins><plugin>
    <groupId>org.apache.maven.plugins</groupId><artifactId>maven-surefire-plugin</artifactId><version>3.5.2</version>
  </plugin></plugins></build>
</project>
"@ | Out-File -Encoding utf8 "$java\pom.xml"
    "package demo; public class Calc { public static int add(int a, int b) { return a + b; } }" | Out-File -Encoding ascii "$java\src\main\java\demo\Calc.java"
    @"
package demo;
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
class CalcTest { @Test void adds() { assertEquals(3, Calc.add(1, 2)); } }
"@ | Out-File -Encoding ascii "$java\src\test\java\demo\CalcTest.java"
    Push-Location $java
    & $mvn -q -B test
    "maven: exit $LASTEXITCODE"
    Pop-Location
} else { "maven: missing" }

$rscript = Find-Tool "Rscript" (Get-ChildItem "C:\Program Files\R" -Directory -ErrorAction SilentlyContinue | Select-Object -Last 1 | ForEach-Object { Join-Path $_.FullName "bin\Rscript.exe" })
if ($rscript) {
    # R_LIBS_USER (win-library\<version>) is where R looks by default; a folder of our own would go unseen.
    & $rscript -e "lib <- Sys.getenv('R_LIBS_USER'); dir.create(lib, recursive = TRUE, showWarnings = FALSE); install.packages('testthat', lib = lib, repos = 'https://cloud.r-project.org')"
    "R testthat: exit $LASTEXITCODE"
} else { "R: missing" }
