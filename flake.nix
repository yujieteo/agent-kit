{
  description = "agent-kit: what the user teaches Claude Code and Codex, installed with hashes";

  # The dotfiles use this flake as an input and put `agent-kit` and `apm` in
  # home.packages. skill-reach (the overlap check) is not packaged: it needs
  # cyclopts >= 5.1.1 and model2vec, which nixpkgs 26.05 does not have. Run
  # that check with `uv tool install 'skill-reach[semantic] @
  # git+https://github.com/google/skill-reach@6568a12'`.
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
          src = pkgs.lib.fileset.toSource {
            root = ./.;
            fileset = pkgs.lib.fileset.unions [
              ./kit ./skills ./.apm ./agents ./apm.yml ./hashes.json ./inventory.tsv
            ];
          };
          agent-kit = pkgs.writeShellApplication {
            name = "agent-kit";
            runtimeInputs = [ pkgs.python3 apm pkgs.git pkgs.gh ];
            text = ''
              export AGENT_KIT_APM=${apm}/bin/apm APM_NON_INTERACTIVE=1
              # apm 0.37.0 fails on a read-only source folder ("open() missing
              # required argument 'flags'", measured), so it gets a copy.
              w=$(mktemp -d "''${TMPDIR:-/tmp}/agent-kit.XXXXXX")
              trap 'chmod -R u+w "$w"; rm -rf "$w"' EXIT
              cp -R ${src} "$w/kit-src"
              chmod -R u+w "$w/kit-src"
              PYTHONPATH="$w/kit-src" python3 -m kit "$@"
            '';
          };
        in
        { inherit apm agent-kit; default = agent-kit; });
    };
}
