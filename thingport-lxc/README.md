# Thingport in a Proxmox LXC, with the consume folder wired up

A script that builds an unprivileged Debian 13 container on a Proxmox VE node, installs Docker CE
in it, and starts [Thingport](https://github.com/TautvydasDerzinskas/Thingport) (a self-hosted
library for 3D-printing models) from a compose file with pinned images. The model library and
the [consume folder](https://thingport.net/docs/guides/consume-folder/) can each sit on a folder
of the node, which is how you put them on a NAS.

Thingport ships as Docker images only, and it is not in the
[community-scripts](https://github.com/community-scripts/ProxmoxVE) collection, so this is the
gap between "here is a compose file" and "it runs on my Proxmox box". Not affiliated with
Thingport. Its own installer and docs are at [thingport.net](https://thingport.net/docs/).

## Status

As of 2026-10-13.

**Run with these exact files:** one build on Proxmox VE 9.2 from the `debian-13-standard_13.6-1`
template, DHCP, with `LIBRARY_DIR` and `CONSUME_DIR` both set to local folders on the node. It
finished with `/api/health` answering 200. A loose STL, a folder holding an STL, and a ZIP were
then copied into the consume folder: three models appeared, the consume folder emptied itself, and
a stray text file was set aside in `Not imported`. The stack came back by itself after
`pct reboot`. Docker was 29.9.0, the app images `sha-6993a4c`.
One line was added to the script after that build (`LC_ALL=C`, to quiet apt's locale warnings) and
checked by itself in the same container, not by a second full build.

**Run for longer, but not from this script:** the same layout (unprivileged Debian 13 container,
Docker CE, this compose file's bind mounts, the library on an SMB share mounted on the node) has
held the author's library of about 1,100 models and 220 GB since 2026-09-19. That one was built by
hand, and it runs older images from before the consume folder existed.

**Not run:** a static address (`NET_IP` / `NET_GW`); the template download; an NFS share; the
consume folder with thousands of files; moving an existing install onto the pinned images here.
The refusal when uid 1000 cannot write to a folder was not triggered in the test.

## Files

- `thingport-lxc.sh`: runs on the Proxmox node. Checks, prints a plan, and with `--execute`
  creates the container, installs Docker, writes the stack and waits for the health check.
- `compose.yaml`: upstream's `docker-compose.deploy.yml` with pinned images, bind mounts instead
  of named volumes, the consume folder mounted, and no default secrets. The script copies it in.

## Requirements

- Proxmox VE (built on 9.2) and a root shell on the node.
- A storage for the root disk, and outbound internet from the container for the Docker packages
  and images.
- About 8 GB of RAM to give it. See *Assumptions that bite*.

## Settings

There is nothing to edit in the files. The script reads environment variables, and refuses to
run without the first two.

| Variable | What it is | Example |
|---|---|---|
| `CTID` | a free guest id | `120` |
| `STORAGE` | storage for the root disk, from `pvesm status` | `local-lvm` |
| `LIBRARY_DIR` | optional. Folder on the node that will hold Thingport's library | `/mnt/nas/thingport-library` |
| `CONSUME_DIR` | optional. Folder on the node that Thingport imports from and empties | `/mnt/nas/thingport-inbox` |
| `PUBLIC_URL` | optional. The address people open, when it is behind a reverse proxy | `https://thingport.example.com` |
| `NET_IP`, `NET_GW` | optional. Default is DHCP | `192.0.2.10/24`, `192.0.2.1` |
| `CT_HOSTNAME`, `CORES`, `MEMORY_MB`, `SWAP_MB`, `DISK_GB`, `BRIDGE` | optional sizing | `thingport`, `4`, `8192`, `512`, `32`, `vmbr0` |
| `TEMPLATE`, `TEMPLATE_STORAGE` | optional. Default: the newest `debian-13-standard` on `local`, downloaded if absent | |
| `AUTH_TOKEN_TTL`, `WEB_PORT`, `TZ` | optional. Default: 30 days, 80, the node's timezone | |

Leave `LIBRARY_DIR` and `CONSUME_DIR` unset and both folders live on the container's own disk.

## Assumptions that bite

- **Folder ownership.** In an unprivileged container, uid 1000 (who the backend runs as) is uid
  101000 on the node. A local folder needs `chown -R 101000:101000`; a CIFS share needs
  `uid=101000,gid=101000` in its mount options. The script proves it by writing a file as uid 1000
  and stops if that fails. It does not read the mode bits, because a network share can report
  any owner it likes.
- **The consume folder deletes what it imports.** Copy into it; never move your only copy. Files
  over 512 MB (`IMPORT_MAX_MB` in `.env`) and files that are not models end up in `Not imported`
  inside it and are never retried. Dropping the same folder twice imports it twice, with " (2)"
  on the names. Check `Not imported` after every large batch: a skipped file is otherwise
  indistinguishable from one that was never there.
- **The library folder belongs to Thingport.** It lays the folder out itself and only knows about
  files it put there. Point `LIBRARY_DIR` at an empty folder, not at your existing collection.
  Your existing collection goes in through the consume folder.
- **The first account is the admin, and registration starts open.** Register straight away,
  then close registration under Users. `/api/health` reports `allow_registrations`.
- **Memory.** On the September 2026 builds the backend converted 3D previews inside the web
  server process, and a few multi-colour `.3mf` files under 1 MB needed several GB each. At 4 GB
  the kernel killed the backend during a bulk import, nothing recorded the failure, and the next
  page view tried again. 8 GB reduced it; a handful of files still exceeded that. Not re-measured
  on the images pinned here.
- **A bind-mounted container cannot be snapshotted.** `pct snapshot` refuses once `LIBRARY_DIR` or
  `CONSUME_DIR` is set. Backups (`vzdump`) still work, and skip the bind-mounted folders.
- **The files are half the library.** Tags, notes, collections, plate order and gallery links are
  only in Postgres. Back up both:
  `docker exec thingport-db-1 pg_dump -U thingport -d thingport --clean --if-exists | gzip > thingport.sql.gz`,
  then `gzip -t` it. The dump holds password hashes and any saved MakerWorld cookie, so treat it
  as a secret.
- **A share that is missing at boot.** If `LIBRARY_DIR` is a subfolder of a network mount and the
  mount is not there, the container refuses to start. That is better than starting on an empty
  folder. Do not create the path by hand under an unmounted mount point to "fix" it.
- **An expired login looks like a hung server.** The page keeps spinning while every API call
  returns 401. Upstream's default lifetime is 12 hours; this sets 30 days. Compare `/api/health`
  (always public) with a signed-in call before restarting anything.
- **Nothing updates the app for you.** `apt` updates Docker, not the images. See *Updating*.

## Install

1. Copy `thingport-lxc.sh` and `compose.yaml` into one folder on the node. `chmod +x thingport-lxc.sh`.
2. If you are using `LIBRARY_DIR` or `CONSUME_DIR`, create the folders and set their ownership as above.
3. Dry run, and read the plan:
   `CTID=120 STORAGE=local-lvm LIBRARY_DIR=/mnt/nas/thingport-library CONSUME_DIR=/mnt/nas/thingport-inbox ./thingport-lxc.sh`
4. The same line with `--execute`. It takes a few minutes, mostly image pulls, and ends by
   printing the address.
5. Open the address and register. Close registration.
6. **Administration → Settings → Consume Folder**: it should say it is watching `/app/consume`.
   Choose *each model file is a separate model* or *each folder is one model*, and save.
7. Copy one folder into the consume folder. Check the result in Thingport before copying the rest.

## Verify it works

- From the node: `pct exec <CTID> -- curl -s http://127.0.0.1/api/health` returns `"ok":true`.
  That route reads the database, so it proves Postgres too.
- `pct exec <CTID> -- docker logs thingport-backend-1 | grep -i consume` says
  `Watching consume folder /app/consume`.
- After copying a test file in: within about ten seconds it is gone from the consume folder,
  present under the library folder, and listed in Thingport. Look at all three.
- `pct reboot <CTID>`, wait a minute, and run the health check again.

## Updating

Upstream tags the app images `:latest` and `sha-<commit>` only, and commits land many times a
day, so the compose file pins both. To move:

1. Back up Postgres (the command above). Updates carry database migrations.
2. Pick a commit. For each of the two images take the newest `sha-` tag at or before it. **The
   two tags are often different strings**, because each image is built only when its own code
   changed.
3. Put `BACKEND_IMAGE=...` and `FRONTEND_IMAGE=...` in `/opt/thingport/stack/.env`.
4. `cd /opt/thingport/stack && docker compose pull && docker compose up -d`, then read
   `docker compose logs backend`: the migrations it applied are named there.

## For AI agents

1. Run the dry run and show the plan before `--execute`. Never choose `CTID` by reading
   `pct list`, which is one node's view; the script asks the cluster, so let it.
2. Read the storage, bridge and folder paths from the node (`pvesm status`, `ip -br link`,
   `findmnt`). Do not reuse the examples here.
3. Never print `/opt/thingport/stack/.env`, and do not `SELECT *` from the `User` table.
4. Prove an import by listing the consume folder, the library folder and the model count, not by
   the notification.
5. Never point `LIBRARY_DIR` or `CONSUME_DIR` at a folder holding the only copy of something.
6. Before changing an image tag, check on the registry that the tag exists for that image.
7. Read the upstream guide for the installed version before giving anyone UI directions.
   The app changes daily and menus move.

## License

MIT, see the [LICENSE](../LICENSE) in the repository root. Thingport itself is AGPL-3.0 and is
not included here; the compose file pulls its published images.
