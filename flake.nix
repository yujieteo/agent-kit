{
  description = "agent-kit: what the user teaches Codex, installed with hashes";

  # Packages: agent-kit (default), apm and skill-reach. agent-kit finds both
  # on its PATH. skill-reach needs three Python packages that nixpkgs 26.05
  # lacks or has too old (cyclopts 5, rich-rst 2, model2vec); they come from
  # their PyPI wheels, pinned by hash.
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-26.05-darwin";

  outputs = { self, nixpkgs }:
    let
      systems = [ "aarch64-darwin" "x86_64-linux" "aarch64-linux" ];
      each = f: nixpkgs.lib.genAttrs systems (s: f nixpkgs.legacyPackages.${s});
    in
    {
      packages = each (pkgs:
        let
          py = pkgs.python3Packages;
          # microsoft/apm 0.37.0. llm-github-models is not in nixpkgs, and
          # no module imports it (read in the source at this commit); the
          # version floors are above nixpkgs 26.05 for filelock only.
          apm = py.buildPythonApplication {
            pname = "apm-cli";
            version = "0.37.0";
            pyproject = true;
            src = pkgs.fetchFromGitHub {
              owner = "microsoft";
              repo = "apm";
              rev = "488a4b1ef7a21c6fecfa51a25a7dd9218b9bb980";
              hash = "sha256-77fjcyyxorBANymqsCjHKmztHJtsXFS8rDtGDsQRI84=";
            };
            build-system = [ py.setuptools ];
            pythonRemoveDeps = [ "llm-github-models" ];
            pythonRelaxDeps = true;
            dependencies = with py; [
              click colorama pyyaml requests truststore python-frontmatter llm toml
              tomlkit rich rich-click watchdog gitpython ruamel-yaml filelock websockets
            ];
            doCheck = false;
            pythonImportsCheck = [ "apm_cli" ];
          };
          wheel = pname: version: hash: deps: py.buildPythonPackage {
            inherit pname version;
            format = "wheel";
            src = py.fetchPypi {
              pname = builtins.replaceStrings [ "-" ] [ "_" ] pname;
              inherit version hash;
              format = "wheel";
              dist = "py3";
              python = "py3";
            };
            dependencies = deps;
            pythonImportsCheck = [ (builtins.replaceStrings [ "-" ] [ "_" ] pname) ];
          };
          rich-rst = wheel "rich-rst" "2.2.0" "sha256-HqHEOBPcSo2GR1/OJ/+3TgraPUZWyfgTC6KlmGgFX+k="
            (with py; [ docutils rich ]);
          cyclopts = wheel "cyclopts" "5.5.2" "sha256-T76GPrrOHGXa/GUgyCIXkVsQPSf70dj80Wjyq8yjoSo="
            (with py; [ attrs docstring-parser rich rich-rst ]);
          model2vec = wheel "model2vec" "0.10.0" "sha256-o5xA3k+CxeDlDBS7uHqTXBxiCU8/Dw2P3o4k9KTzWxY="
            (with py; [ jinja2 joblib numpy safetensors tokenizers tqdm huggingface-hub ]);
          # google/skill-reach, with its [semantic] extra. The rich and pydantic
          # floors are a minor version above nixpkgs; the tests below run it.
          skill-reach = py.buildPythonApplication {
            pname = "skill-reach";
            version = "0.1.0";
            pyproject = true;
            src = pkgs.fetchFromGitHub {
              owner = "google";
              repo = "skill-reach";
              rev = "6568a12173d4b91c79e3d3844cdfa469f851e5da";
              hash = "sha256-JQmQyVMAv9QK4wDGKZThNRKrAH3fgOeYpodPmb0a9bo=";
            };
            build-system = [ py.hatchling ];
            pythonRelaxDeps = true;
            dependencies = (with py; [ pydantic pyyaml rich huggingface-hub ]) ++ [ cyclopts model2vec ];
            doCheck = false;
            pythonImportsCheck = [ "reach" ];
          };
          src = pkgs.lib.fileset.toSource {
            root = ./.;
            fileset = pkgs.lib.fileset.unions [
              ./kit ./skills ./.apm ./agents ./apm.yml ./hashes.json
            ];
          };
          agent-kit = pkgs.writeShellApplication {
            name = "agent-kit";
            runtimeInputs = [ pkgs.python3 apm skill-reach pkgs.git pkgs.gh ];
            text = ''
              export AGENT_KIT_APM=${apm}/bin/apm AGENT_KIT_REACH=${skill-reach}/bin/reach APM_NON_INTERACTIVE=1
              # AGENT_KIT_REPO=/path/to/clone runs the kit of that clone, in place:
              # lock writes its hashes.json, and replay and search-proof find
              # its git history and results/.
              r=''${AGENT_KIT_REPO:-}
              if [ -n "$r" ]; then
                if [ ! -f "$r/kit/__main__.py" ]; then
                  echo "agent-kit: AGENT_KIT_REPO=$r is not a clone of agent-kit (no kit/__main__.py)" >&2
                  exit 2
                fi
                PYTHONPATH=$(cd "$r" && pwd) exec python3 -m kit "$@"
              fi
              # Otherwise it runs from a copy of the flake's source, deleted on
              # exit: apm 0.37.0 fails on a read-only source folder ("open()
              # missing required argument 'flags'", measured). The copy has no
              # .git, tests or results/, so kit/__main__.py refuses the commands
              # that need them (lock without --check, replay, search-proof).
              export AGENT_KIT_COPY=1
              w=$(mktemp -d "''${TMPDIR:-/tmp}/agent-kit.XXXXXX")
              trap 'chmod -R u+w "$w"; rm -rf "$w"' EXIT
              cp -R ${src} "$w/kit-src"
              chmod -R u+w "$w/kit-src"
              PYTHONPATH="$w/kit-src" python3 -m kit "$@"
            '';
          };
        in
        { inherit apm skill-reach agent-kit; default = agent-kit; });
    };
}
