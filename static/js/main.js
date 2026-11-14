const SCHOOL = { lat: 41.32585, lng: 69.26742 };

const PHOTO = {
  chinor: "https://images.unsplash.com/photo-1502082553048-f009c37129b9?auto=format&fit=crop&w=1200&q=80",
  eman: "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?auto=format&fit=crop&w=1200&q=80",
  archa: "https://images.unsplash.com/photo-1542273917363-3b1817f69a2d?auto=format&fit=crop&w=1200&q=80",
  kashtan: "https://images.unsplash.com/photo-1469474968028-56623f02e42e?auto=format&fit=crop&w=1200&q=80",
  terak: "https://images.unsplash.com/photo-1502086223501-7ea6ecd79368?auto=format&fit=crop&w=1200&q=80",
  qayragoch: "https://images.unsplash.com/photo-1473448917267-20285e4c1c2c?auto=format&fit=crop&w=1200&q=80",
};

function photoUrl(key) {
  return PHOTO[key] || PHOTO.chinor;
}

function statusColor(status) {
  if (status === "Xavfli") return "#ef4444";
  if (status === "Parvarish talab") return "#f59e0b";
  return "#22c55e";
}

function treeIcon(status) {
  const color = statusColor(status);
  return L.divIcon({
    className: "custom-pin",
    html: `<div style="width:28px;height:36px;filter:drop-shadow(0 4px 6px rgba(0,0,0,.25))">
      <svg viewBox="0 0 28 36" width="28" height="36">
        <path d="M14 34s10-11.2 10-18A10 10 0 1 0 4 16c0 6.8 10 18 10 18z" fill="${color}"/>
        <circle cx="14" cy="15" r="5.2" fill="#fff"/>
        <path d="M14 10.5c2.4 1.6 3.4 3.4 3.2 5.2-1.6-.4-2.6.2-3.2 1.4-.6-1.2-1.6-1.8-3.2-1.4-.2-1.8.8-3.6 3.2-5.2z" fill="${color}"/>
      </svg>
    </div>`,
    iconSize: [28, 36],
    iconAnchor: [14, 34],
    popupAnchor: [0, -28],
  });
}

function schoolIcon() {
  return L.divIcon({
    className: "custom-pin",
    html: `<div style="background:#fff;color:#16301d;border:2px solid #166534;border-radius:12px;padding:6px 8px;font-weight:800;font-size:12px;box-shadow:0 8px 16px rgba(0,0,0,.2)">🎓 237-maktab</div>`,
    iconSize: [110, 28],
    iconAnchor: [55, 14],
  });
}

function addBaseLayers(map, satellite = false) {
  const osm = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap",
  });
  const esri = L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 19, attribution: "Tiles &copy; Esri" }
  );
  (satellite ? esri : osm).addTo(map);
  return { osm, esri };
}

function bindTreePopup(marker, tree) {
  const age = 2026 - Number(tree.planted_year || tree.plantedYear || 2000);
  marker.bindPopup(
    `<b>${tree.species_name || tree.speciesName}</b><br>
     ${tree.health_status || tree.healthStatus}<br>
     ${age} yil · ${tree.height_m || tree.heightM || "-"} m<br>
     <a href="/daraxt/${tree.id}">Pasportni ko‘rish →</a>`
  );
}

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("menuBtn");
  const nav = document.getElementById("nav");
  if (btn && nav) btn.addEventListener("click", () => nav.classList.toggle("open"));

  document.querySelectorAll("[data-photo]").forEach((el) => {
    el.style.backgroundImage = `url('${photoUrl(el.dataset.photo)}')`;
  });
});
