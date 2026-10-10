# Hosting AdFreeShono on the web

You need: a small server, a domain name, and about 30 minutes. Your PC does not need to be on.

## 1. Get a server (Ubuntu 24.04)
- Oracle Cloud "Always Free": free. Arm VM (VM.Standard.A1.Flex, currently up to 2 CPUs / 12 GB RAM), 200 GB disk, 10 TB/month outbound traffic.
  Free servers sometimes show "out of capacity" when you create them (try again later or another region) and idle ones can be reclaimed, so keep your music originals.
- Hetzner Cloud: about $5-7/month, 20 TB traffic included. Check their price page (prices changed in June 2026). Small plans have ~40 GB disk; add a volume for a big library.

## 2. Get a domain name
Free: create a name at duckdns.org and point it to your server's IP address. Or buy a domain (about $10/year) and add an A record to the server IP.
HTTPS needs a domain; it will not work with a bare IP address.

## 3. Open the web ports
Open TCP ports 80 and 443. On Oracle you must do it in two places: the network "Security List" of your VCN, and the server's own firewall:

    sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
    sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
    sudo apt install -y iptables-persistent && sudo netfilter-persistent save

## 4. Install Docker on the server
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker $USER      # then log out and back in

## 5. Put the project on the server
Either push it to a PRIVATE GitHub repo and `git clone` it on the server, or copy the zip:

    scp AdFreeShono.zip youruser@SERVER_IP:~
    ssh youruser@SERVER_IP
    sudo apt install -y unzip && unzip AdFreeShono.zip && cd AdFreeShono

## 6. Create the settings file
    cp .env.example .env
    python3 -c "import secrets; print(secrets.token_urlsafe(48))"    # copy the output
    nano .env                      # set DOMAIN, ADMIN_USERNAME, ADMIN_PASSWORD, SECRET_KEY

The app refuses to start while ADMIN_PASSWORD / SECRET_KEY are placeholders or too weak.
ADMIN_USERNAME / ADMIN_PASSWORD create YOUR admin account the first time the app starts.
After that they are ignored: change your password from the Account page instead.

## 7. Start it
    docker compose up -d --build
    docker compose logs -f app     # Ctrl+C to stop watching

Open https://YOUR-DOMAIN and log in with your admin username and password. The first start can take a minute while the HTTPS certificate is issued.

## 8. Add your friends
Open the **Admin** page, fill in a username and a password (10+ characters), and press Create account.
Send them the username, the password and the web address privately. They can change their own password under **Account**.
- Everyone shares ONE library: songs anyone uploads are visible to all.
- Playlists, likes and play history are private to each person (not even the admin sees playlists in the app).
- Friends can upload (up to MEMBER_QUOTA_MB each, default 5000), and can edit or delete only the songs they uploaded.
- Only admins can scan server folders, manage accounts, or change songs they did not upload.
- Deleting a song removes it for everyone, including from other people's playlists.
- To remove a friend's access, press Disable on the Admin page. It signs them out immediately. Their uploaded songs stay.
- The same song file cannot be uploaded twice.

## 9. Add your music
- Bulk: copy your folders into the `music` folder next to docker-compose.yml, then open Upload and scan the folder `/music`.
  Example from your PC: `scp -r "D:\Music" youruser@SERVER_IP:~/AdFreeShono/music/`
  That folder is mounted read-only, so the app can never delete or change those files.
- Or drag files into the Upload page. They are stored on the server in `data/`.

## Everyday commands
    docker compose up -d --build   # after changing code or pulling updates
    docker compose logs -f app     # see errors
    docker compose restart app
    docker compose down            # stop everything

## Account recovery (forgot the admin password)
    docker compose exec -it app python scripts/manage_users.py reset-password YOURNAME
Other commands: list, create NAME (add --admin for another admin), disable NAME, enable NAME.

## Backups
    docker compose exec app python scripts/backup.py --dest /app/data/backups --no-music

Then copy `data/backups/` (and `data/media/audio/` if you upload through the website) to your PC with scp.
Keep your original music on your PC; the server copy is a convenience, not a backup.

## Troubleshooting
- "Refusing to start": read the message, fix .env, run `docker compose up -d` again.
- Site not loading / no certificate: check the domain points to the server IP and ports 80/443 are open (step 3).
- Locked out after wrong passwords: wait 15 minutes, or `docker compose restart app`.
- A friend cannot log in: check the username (not case sensitive) and that the account is not disabled (Admin page).
- Disk filling up: friends' uploads live in `data/media/audio`. Lower MEMBER_QUOTA_MB in .env and run `docker compose up -d`.
