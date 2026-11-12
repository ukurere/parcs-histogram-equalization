# Гайд: PARCS-Python на Google Cloud (master + 4 workers)

Перевірено 13.11.2026. Команди для **PowerShell на Windows**
(у bash / Cloud Shell — те саме, змінні через `export`, перенос рядка `\` замість `` ` ``).

> ⚠️ Команда з методички `gcloud compute instances create-with-container` **більше не працює**:
> `The option to deploy a container during VM instance creation that relies on a container startup agent is discontinued.`
> Нижче — робоча заміна: VM з **Container-Optimized OS** + startup-скрипт, що запускає той самий
> Docker-образ `hummer12007/parcs-node` (скрипти в [`gcp/`](../gcp)).

## 0. Один раз: встановити gcloud

```powershell
winget install --id Google.CloudSDK --source winget
# без прав адміністратора: розпакувати https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-windows-x86_64.zip
gcloud auth login
```

Якщо `gcloud auth login` падає з `CERTIFICATE_VERIFY_FAILED` — HTTPS перехоплює антивірус
(у мене Avast Web Shield). Додати його корінь (з Windows-сховища) до CA-бандла gcloud:

```powershell
$sdk = "<шлях до google-cloud-sdk>"
$av  = Get-ChildItem Cert:\LocalMachine\Root | ? Subject -like '*Avast Web/Mail Shield Root*'
$pem = "-----BEGIN CERTIFICATE-----`n" + [Convert]::ToBase64String($av.RawData,'InsertLineBreaks') + "`n-----END CERTIFICATE-----`n"
$out = "$env:LOCALAPPDATA\gcloud-ca-bundle.pem"
[IO.File]::WriteAllText($out, [IO.File]::ReadAllText("$sdk\lib\third_party\botocore\cacert.pem") + "`n" + $pem)
gcloud config set core/custom_ca_certs_file $out
```

## 1. Проєкт, білінг, API, зона

```powershell
$PROJECT = "parcs-histeq-$(Get-Random -Minimum 10000 -Maximum 99999)"
gcloud projects create $PROJECT
gcloud config set project $PROJECT
# Billing: https://console.cloud.google.com/billing → Start free trial ($300),
# потім Billing → Linked account → прив'язати акаунт до проєкту
gcloud services enable compute.googleapis.com
gcloud config set compute/region europe-central2
gcloud config set compute/zone europe-central2-a
```

## 2. Фаєрвол VPC

Мережа `default` вже має `default-allow-internal` (master ↔ workers). Ззовні — лише 8080 і лише своя IP:

```powershell
$MYIP = (Invoke-RestMethod https://api.ipify.org)
gcloud compute firewall-rules create parcs-web --network=default --direction=INGRESS `
  --allow=tcp:8080 --source-ranges="$MYIP/32"
```

## 3. Master

```powershell
gcloud compute instances create master --machine-type=e2-medium `
  --image-family=cos-stable --image-project=cos-cloud `
  --metadata-from-file=startup-script=gcp/startup-master.sh

$MASTER_IP  = gcloud compute instances describe master --format="get(networkInterfaces[0].networkIP)"
$MASTER_EXT = gcloud compute instances describe master --format="get(networkInterfaces[0].accessConfigs[0].natIP)"
```

`gcp/startup-master.sh` відкриває порти в iptables самої VM (у COS за замовчуванням дозволено лише SSH)
і запускає `docker run --net=host -e PARCS_ARGS=master hummer12007/parcs-node`.

## 4. Workers (4 шт.)

```powershell
gcloud compute instances create worker1 worker2 worker3 worker4 --machine-type=e2-medium `
  --image-family=cos-stable --image-project=cos-cloud `
  --metadata=parcs-master-ip=$MASTER_IP `
  --metadata-from-file=startup-script=gcp/startup-worker.sh

gcloud compute instances list
```

Через ~1 хв: `http://<MASTER_EXT>:8080` → вкладка **Nodes** — 4 воркери.

## 5. Запуск задачі

**Вручну:** `Add Job` → Solution File = `solver/histeq_solver.py`, Input File = `data/input_rgb.txt` →
`Jobs` → `Output` (PPM-зображення; час фаз — у його заголовку).
Кількість воркерів — кнопками **Disable/Enable** на сторінці Nodes.

**Автоматично (N = 1…4, по 3 прогони):**

```powershell
pip install requests numpy pillow matplotlib
python tools/make_input.py --out data/input_rgb.txt --mode RGB --size 3000x2000
python tools/benchmark.py --master "http://${MASTER_EXT}:8080" --input data/input_rgb.txt `
  --workers 1 2 3 4 --repeat 3 --csv results/gcp.csv --save-output results/gcp_out
python tools/plot_results.py results/gcp.csv --title "GCP: master + 4x e2-medium, 3000x2000 RGB"
```

## 6. Діагностика

```powershell
gcloud compute instances get-serial-port-output master | Select-String startup-script   # лог startup-скрипта
gcloud compute ssh master      # всередині: docker ps ; docker logs -f parcs
```

## 7. Прибрати за собою

```powershell
gcloud compute instances delete master worker1 worker2 worker3 worker4 --quiet
gcloud compute firewall-rules delete parcs-web --quiet
# або все одразу: gcloud projects delete $PROJECT
```
