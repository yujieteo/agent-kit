{
  description = "agent-kit: shared agent skills, installed and verified by SHA-256";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-26.05-darwin";

  outputs = { self, nixpkgs }:
    let
      systems = [ "aarch64-darwin" "x86_64-linux" "aarch64-linux" ];
      each = f: nixpkgs.lib.genAttrs systems (s: f nixpkgs.legacyPackages.${s});
    in
    {
      packages = each (pkgs:
        let
          src = pkgs.lib.fileset.toSource {
            root = ./.;
            fileset = pkgs.lib.fileset.unions [
              ./kit ./skills ./.apm
            ];
          };
          agent-kit = pkgs.writeShellApplication {
            name = "agent-kit";
            runtimeInputs = [ pkgs.python3 pkgs.git pkgs.gh ];
            text = ''
              r=''${AGENT_KIT_REPO:-}
              if [ -n "$r" ]; then
                if [ ! -f "$r/kit/__main__.py" ]; then
                  echo "agent-kit: AGENT_KIT_REPO=$r is not a clone of agent-kit (no kit/__main__.py)" >&2
                  exit 2
                fi
                PYTHONPATH=$(cd "$r" && pwd) exec python3 -m kit "$@"
              fi
              export AGENT_KIT_COPY=1
              PYTHONPATH=${src} exec python3 -m kit "$@"
            '';
          };
        in
        { inherit agent-kit; default = agent-kit; });
    };
}
