#!/usr/bin/env bash
# Build a Thingport LXC on a Proxmox VE node: an unprivileged Debian 13 container, Docker CE
# from Docker's own apt repository, and the compose stack in compose.yaml next to this script.
#
# Run it on the node, as root, from the folder holding both files:
#
#   CTID=120 STORAGE=local-lvm ./thingport-lxc.sh             # dry run: prints the plan
#   CTID=120 STORAGE=local-lvm ./thingport-lxc.sh --execute   # builds it
#
# Required:  CTID      a free guest id
#            STORAGE   where the root disk goes (see `pvesm status`)
# Optional:  CT_HOSTNAME (thingport)  CORES (4)  MEMORY_MB (8192)  SWAP_MB (512)  DISK_GB (32)
#            BRIDGE (vmbr0)  NET_IP (dhcp, or CIDR like 192.0.2.10/24)  NET_GW (with a static NET_IP)
#            TEMPLATE      a volid from `pveam list <storage>`; default: newest debian-13-standard
#            TEMPLATE_STORAGE (local)   where to look for, or download, that template
#            LIBRARY_DIR   a folder ON THE NODE to hold the model library (a NAS mount, usually)
#            CONSUME_DIR   a folder ON THE NODE that Thingport watches and imports from
#            PUBLIC_URL    the address people will open, if it sits behind a reverse proxy
#            AUTH_TOKEN_TTL (2592000 = 30 days)  WEB_PORT (80)  TZ (the node's)
#
# Without LIBRARY_DIR / CONSUME_DIR both folders live on the container's own disk.
set -euo pipefail

EXECUTE=0
case "${1:-}" in
  "") ;;
  --execute) EXECUTE=1 ;;
  *) echo "Usage: CTID=<id> STORAGE=<storage> $0 [--execute]" >&2; exit 2 ;;
esac

fail() { echo "ERROR: $*" >&2; exit 1; }
say() { printf '\n== %s\n' "$*"; }

: "${CTID:?set CTID to a free guest id}"
: "${STORAGE:?set STORAGE to the storage for the root disk (pvesm status)}"
CT_HOSTNAME=${CT_HOSTNAME:-thingport}
CORES=${CORES:-4}
# tune: 8 GB. Thingport builds 3D previews inside the web server process, and some .3mf files
# need several GB to convert. At 4 GB the kernel killed the backend during a bulk import.
MEMORY_MB=${MEMORY_MB:-8192}
SWAP_MB=${SWAP_MB:-512}
DISK_GB=${DISK_GB:-32}
BRIDGE=${BRIDGE:-vmbr0}
NET_IP=${NET_IP:-dhcp}
NET_GW=${NET_GW:-}
TEMPLATE=${TEMPLATE:-}
TEMPLATE_STORAGE=${TEMPLATE_STORAGE:-local}
LIBRARY_DIR=${LIBRARY_DIR:-}
CONSUME_DIR=${CONSUME_DIR:-}
PUBLIC_URL=${PUBLIC_URL:-}
AUTH_TOKEN_TTL=${AUTH_TOKEN_TTL:-2592000}
WEB_PORT=${WEB_PORT:-80}
TZ_NAME=${TZ:-$(timedatectl show -p Timezone --value 2>/dev/null || echo UTC)}

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
COMPOSE_SRC="$SCRIPT_DIR/compose.yaml"

# ---------------------------------------------------------------- checks (dry run does these too)
[ "$(id -u)" -eq 0 ] || fail "run this as root on the Proxmox node"
for tool in pct pvesh pveam pvesm; do
  command -v "$tool" > /dev/null || fail "$tool not found: this runs on a Proxmox VE node, not inside a guest"
done
[ -f "$COMPOSE_SRC" ] || fail "compose.yaml must sit next to this script ($COMPOSE_SRC)"
[[ "$CTID" =~ ^[0-9]+$ ]] || fail "CTID must be a number"
for n in CORES MEMORY_MB SWAP_MB DISK_GB WEB_PORT AUTH_TOKEN_TTL; do
  [[ "${!n}" =~ ^[0-9]+$ ]] || fail "$n must be a whole number"
done
# These three are written into .env unquoted, so keep them to plain characters.
[[ "$TZ_NAME" =~ ^[A-Za-z0-9_+/-]+$ ]] || fail "TZ looks wrong: $TZ_NAME"
[[ "$CT_HOSTNAME" =~ ^[A-Za-z0-9-]+$ ]] || fail "CT_HOSTNAME may hold letters, digits and hyphens only"
[[ -z "$PUBLIC_URL" || "$PUBLIC_URL" =~ ^https?://[A-Za-z0-9._:/-]+$ ]] || fail "PUBLIC_URL must be a plain http(s) URL"

# `pct list` only shows this node's containers. On a cluster an id can be taken by a VM, or by a
# guest on another node, and still look free there. This asks the cluster.
pvesh get /cluster/nextid --vmid "$CTID" > /dev/null 2>&1 || fail "guest id $CTID is already in use"
pvesm status --storage "$STORAGE" > /dev/null 2>&1 || fail "storage '$STORAGE' not found (pvesm status)"

for pair in "LIBRARY_DIR:$LIBRARY_DIR" "CONSUME_DIR:$CONSUME_DIR"; do
  name=${pair%%:*}; dir=${pair#*:}
  [ -z "$dir" ] && continue
  [ -d "$dir" ] || fail "$name=$dir is not a directory on this node"
  [[ "$dir" == /* ]] || fail "$name must be an absolute path"
  # A comma would end the path inside the mount-point option.
  [[ "$dir" != *,* ]] || fail "$name must not contain a comma"
done
[ -z "$LIBRARY_DIR" ] || [ "$LIBRARY_DIR" != "$CONSUME_DIR" ] || fail "LIBRARY_DIR and CONSUME_DIR must be different folders"

if [ -z "$TEMPLATE" ]; then
  TEMPLATE=$(pveam list "$TEMPLATE_STORAGE" 2>/dev/null | awk '$1 ~ /debian-13-standard/ {print $1}' | sort -V | tail -n1)
fi
TEMPLATE_DOWNLOAD=""
if [ -z "$TEMPLATE" ]; then
  TEMPLATE_DOWNLOAD="newest debian-13-standard, into '$TEMPLATE_STORAGE'"
fi

NET0="name=eth0,bridge=$BRIDGE,ip=$NET_IP"
[ -z "$NET_GW" ] || NET0="$NET0,gw=$NET_GW"

# ---------------------------------------------------------------- the plan
say "Plan"
cat << EOF
  container    $CTID  '$CT_HOSTNAME'  unprivileged, nesting=1,keyctl=1, onboot
  size         $CORES vCPU / $MEMORY_MB MB RAM / $SWAP_MB MB swap / $DISK_GB GB on $STORAGE
  network      $NET0
  template     ${TEMPLATE:-<download: $TEMPLATE_DOWNLOAD>}
  library      ${LIBRARY_DIR:-<container disk>}  ->  /mnt/models  ->  /app/storage
  consume      ${CONSUME_DIR:-<container disk>}  ->  /mnt/consume ->  /app/consume
  stack        /opt/thingport/stack (compose.yaml + a generated .env, mode 600)
  database     /opt/thingport/data/postgres (always on the container's disk)
  timezone     $TZ_NAME     web port $WEB_PORT     login lifetime ${AUTH_TOKEN_TTL}s
  public url   ${PUBLIC_URL:-<none>}
EOF

if [ "$EXECUTE" -ne 1 ]; then
  say "Dry run: nothing was changed. Add --execute to build it."
  exit 0
fi

# ---------------------------------------------------------------- build
if [ -n "$TEMPLATE_DOWNLOAD" ]; then
  say "Downloading the Debian 13 template"
  pveam update > /dev/null
  name=$(pveam available --section system | awk '$2 ~ /^debian-13-standard/ {print $2}' | sort -V | tail -n1)
  [ -n "$name" ] || fail "no debian-13-standard template on offer (pveam available --section system)"
  pveam download "$TEMPLATE_STORAGE" "$name"
  TEMPLATE="$TEMPLATE_STORAGE:vztmpl/$name"
fi

say "Creating container $CTID"
create_args=(
  "$CTID" "$TEMPLATE"
  --hostname "$CT_HOSTNAME" --ostype debian --unprivileged 1
  # Docker inside an unprivileged container needs both of these.
  --features nesting=1,keyctl=1
  --cores "$CORES" --memory "$MEMORY_MB" --swap "$SWAP_MB"
  --rootfs "$STORAGE:$DISK_GB"
  --net0 "$NET0"
  --timezone "$TZ_NAME"
  --onboot 1
)
mp=0
if [ -n "$LIBRARY_DIR" ]; then create_args+=("--mp$mp" "$LIBRARY_DIR,mp=/mnt/models"); mp=$((mp + 1)); fi
if [ -n "$CONSUME_DIR" ]; then create_args+=("--mp$mp" "$CONSUME_DIR,mp=/mnt/consume"); fi
pct create "${create_args[@]}"
pct start "$CTID"

say "Waiting for the container's network"
for i in $(seq 1 30); do
  pct exec "$CTID" -- getent hosts download.docker.com > /dev/null 2>&1 && break
  [ "$i" -lt 30 ] || fail "container $CTID has no working DNS after 60 s; fix its network, then re-run the steps below by hand"
  sleep 2
done

# The guest half goes in on stdin with a quoted heredoc. Passing it as `pct exec ... sh -c "..."`
# lets the NODE's shell expand the variables and globs first, which runs half of it in the wrong place.
say "Installing Docker CE in the container"
pct exec "$CTID" -- bash -s << 'GUEST'
set -euo pipefail
# The template ships no locales; without this apt prints a screen of perl warnings.
export DEBIAN_FRONTEND=noninteractive LC_ALL=C
apt-get update -qq
apt-get install -y -qq ca-certificates curl openssl > /dev/null
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
cat > /etc/apt/sources.list.d/docker.sources << EOF
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: $VERSION_CODENAME
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin > /dev/null
docker --version
docker compose version
# uid/gid 1000 is who the backend runs as (PUID/PGID). On the container's own disk these are
# plain directories; with LIBRARY_DIR / CONSUME_DIR they are already mount points.
mkdir -p /opt/thingport/stack /opt/thingport/data/postgres /opt/thingport/backups /mnt/models /mnt/consume
GUEST

say "Checking that uid 1000 can write to the library and consume folders"
for dir in /mnt/models /mnt/consume; do
  if ! pct exec "$CTID" -- mountpoint -q "$dir"; then
    pct exec "$CTID" -- chown 1000:1000 "$dir"
  fi
  # Proven by writing, not by reading the mode bits: a network share can show any owner it likes.
  if ! pct exec "$CTID" -- setpriv --reuid 1000 --regid 1000 --clear-groups \
      sh -c 'f="$1/.thingport-write-test" && touch "$f" && rm "$f"' sh "$dir"; then
    cat >&2 << EOF
ERROR: uid 1000 inside the container cannot write to $dir.
  In an unprivileged container, uid 1000 is uid 101000 on the node. So on the node:
    a local folder   chown -R 101000:101000 <the folder>
    a CIFS mount     mount it with uid=101000,gid=101000
    an NFS export    map or squash to 101000 on the server
  Container $CTID exists and Docker is installed. Fix the ownership, then re-run from
  "Writing the stack" by hand, or 'pct destroy $CTID' and start again.
EOF
    exit 1
  fi
done

say "Writing the stack"
pct push "$CTID" "$COMPOSE_SRC" /opt/thingport/stack/compose.yaml --perms 644
# The two secrets are generated inside the container and never leave it: they do not pass
# through this script's variables, the node's process list or the terminal.
pct exec "$CTID" -- env TP_TZ="$TZ_NAME" TP_URL="$PUBLIC_URL" TP_TTL="$AUTH_TOKEN_TTL" TP_PORT="$WEB_PORT" bash -s << 'GUEST'
set -euo pipefail
cd /opt/thingport/stack
[ ! -e .env ] || { echo "ERROR: .env already exists; not overwriting it" >&2; exit 1; }
umask 077
cat > .env << EOF
# Generated on this container. Keep it: the database password is needed to start Thingport again.
AUTH_SECRET=$(openssl rand -hex 32)
POSTGRES_PASSWORD=$(openssl rand -hex 24)
POSTGRES_USER=thingport
POSTGRES_DB=thingport
PUID=1000
PGID=1000
WEB_PORT=$TP_PORT
PUBLIC_URL=$TP_URL
AUTH_TOKEN_TTL=$TP_TTL
TZ=$TP_TZ
EOF
chmod 600 .env
docker compose config --quiet
docker compose pull --quiet
docker compose up -d
GUEST

say "Waiting for Thingport to answer"
# /api/health reads the settings table, so a 200 here means the API and Postgres are both up.
ok=0
for i in $(seq 1 60); do
  if pct exec "$CTID" -- curl -fsS -o /dev/null "http://127.0.0.1:$WEB_PORT/api/health" 2> /dev/null; then ok=1; break; fi
  sleep 3
done
if [ "$ok" -ne 1 ]; then
  pct exec "$CTID" -- sh -c 'cd /opt/thingport/stack && docker compose ps && docker compose logs --tail 40 backend' >&2 || true
  fail "Thingport did not answer on /api/health within 3 minutes; the log above is the backend's"
fi

ip=$(pct exec "$CTID" -- hostname -I | awk '{print $1}')
port_suffix=""; [ "$WEB_PORT" = "80" ] || port_suffix=":$WEB_PORT"
say "Done"
cat << EOF
  Thingport is up at http://$ip$port_suffix

  Do these now:
   1. Open it and register. THE FIRST ACCOUNT BECOMES THE ADMIN, and registration is open
      to anyone who can reach that address until you close it (Users, in the admin menu).
   2. Administration -> Settings -> Consume Folder: pick the import mode and save. Then copy
      (never move) files into ${CONSUME_DIR:-/mnt/consume inside the container}.
   3. Reboot the container once and check it comes back: pct reboot $CTID
EOF
