# Branch Setup Guide — Super POS
Follow these steps on every new machine (Linux Ubuntu 24.04 recommended).

---

## Step 1 — Install System Dependencies (Linux only)

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3.12 python3.12-venv python3-pip git -y
sudo apt install libxcb-cursor0 libxcb1 libx11-6 libgl1 libglib2.0-0 libegl1 libfontconfig1 libdbus-1-3 -y
```

For USB ESC/POS printer:
```bash
sudo bash -c 'echo "SUBSYSTEM==\"usb\", ATTRS{bDeviceClass}==\"07\", MODE=\"0666\"" > /etc/udev/rules.d/99-usb-printer.rules'
sudo udevadm control --reload-rules
```

---

## Step 2 — Clone the App

```bash
git clone https://github.com/elie-t/Super-pos.git
cd Super-pos
```

---

## Step 3 — Create Virtual Environment & Install Packages

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Step 4 — Create the .env File

```bash
nano .env
```

Paste the following (fill in the values from Supabase dashboard):

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=eyJ...your-service-role-key...
BRANCH_ID=your-warehouse-uuid-from-supabase
ONLINE_DB_URL=postgresql://postgres.xxx:password@aws-xxx.pooler.supabase.com:6543/postgres
```

Save with `Ctrl+O`, `Enter`, `Ctrl+X`.

> **BRANCH_ID** = the UUID of this branch's warehouse from the `warehouses_central` table in Supabase.
> Each branch machine must have its own unique BRANCH_ID.

Remove Windows line endings if file was copied from Windows/Mac:
```bash
sed -i 's/\r//' .env
```

---

## Step 5 — Pull Users & Master Data from Supabase

```bash
source venv/bin/activate
python -c "from sync.service import pull_users; pull_users(); print('Users pulled')"
```

---

## Step 6 — Run the App

```bash
source venv/bin/activate
python main.py
```

Log in with your admin credentials. Then go to **Settings → Force Push / Pull Now** to sync all items, prices, customers, and stock.

---

## Step 7 — Configure the App (first time only)

Inside the app:
1. **Settings** → set shop name, address, phone, LBP rate
2. **Settings** → configure printer (ESC/POS USB or Windows Qt)
3. **User Management** → verify users synced correctly, set Power User flag if needed
4. **POS** → confirm the correct branch/warehouse is auto-selected

---

## Updating the App (after changes are pushed)

```bash
cd ~/Super-pos
source venv/bin/activate
git pull origin main
python main.py
```

---

## Going Live (one-time reset after testing)

Run this ONCE to wipe all test transactions before going live:
```bash
python reset_transactions.py
```
Type `YES` when prompted. Items, users, and settings are kept. Stock resets to 0 — do a first inventory count after.

---

## Shortcuts Reference

| Key | Action |
|-----|--------|
| F8  | Pay |
| F9  | Print last receipt |
| F10 | Price check |
| F2  | Hold sale |
| F3  | Recall held sale |
| F4  | New sale |
| Del | Void line (requires elevation) |
