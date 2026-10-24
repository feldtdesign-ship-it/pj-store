/* Proof of concept: the tech-pack Bella tee with this product's print projected on the chest. Preview only. */
(function () {
  var el = document.querySelector('[data-tee3d]');
  if (!el || !window.THREE || !THREE.GLTFLoader) return;
  var artSrc = el.getAttribute('data-art'), colour = el.getAttribute('data-color') || '#EFEDE6';
  var printW = parseFloat(el.getAttribute('data-print-w') || '0.40');   // print width as a share of the tee's full width (sleeve to sleeve)
  var printTop = parseFloat(el.getAttribute('data-print-top') || '0.13'); // print top, share of tee length down from the collar
  var W = el.clientWidth, H = el.clientHeight || W;
  var renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2)); renderer.setSize(W, H);
  renderer.outputEncoding = THREE.sRGBEncoding; el.appendChild(renderer.domElement);
  var scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(26, W / H, 1, 2000);
  scene.add(new THREE.HemisphereLight(0xffffff, 0xd8d4ca, 0.95));
  var key = new THREE.DirectionalLight(0xfff8ee, 0.55); key.position.set(22, 34, 40); scene.add(key);
  var rim = new THREE.DirectionalLight(0xffffff, 0.25); rim.position.set(-30, 12, -30); scene.add(rim);
  var controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enablePan = false; controls.enableZoom = false; controls.enableDamping = true; controls.dampingFactor = 0.08;
  controls.autoRotate = true; controls.autoRotateSpeed = 0.9; controls.minPolarAngle = 1.2; controls.maxPolarAngle = 1.75;

  var TW = 1024, TH = 1024, front = document.createElement('canvas'); front.width = TW; front.height = TH;
  var frontTex = new THREE.CanvasTexture(front); frontTex.encoding = THREE.sRGBEncoding;
  function artBox(img) {   // bounding box of the ink on a white scan, so the paper margin is not part of the print size
    var s = 256, cv = document.createElement('canvas'); cv.width = s; cv.height = s;
    var c = cv.getContext('2d'); c.drawImage(img, 0, 0, s, s);
    var d = c.getImageData(0, 0, s, s).data, x0 = s, y0 = s, x1 = 0, y1 = 0;
    for (var y = 0; y < s; y++) for (var x = 0; x < s; x++) { var i = (y * s + x) * 4; if (d[i] + d[i + 1] + d[i + 2] < 690) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; } }
    if (x1 <= x0 || y1 <= y0) return { x: 0, y: 0, w: img.naturalWidth, h: img.naturalHeight };
    var fx = img.naturalWidth / s, fy = img.naturalHeight / s;
    return { x: x0 * fx, y: y0 * fy, w: (x1 - x0 + 1) * fx, h: (y1 - y0 + 1) * fy };
  }
  function paint(img, aspect) {
    var c = front.getContext('2d'); c.fillStyle = colour; c.fillRect(0, 0, TW, TH);
    if (img) {
      var b = artBox(img), w = TW * printW, h = w * (b.h / b.w) * aspect, x = (TW - w) / 2, y = TH * printTop;
      c.globalCompositeOperation = 'multiply'; c.drawImage(img, b.x, b.y, b.w, b.h, x, y, w, h); c.globalCompositeOperation = 'source-over';
    }
    frontTex.needsUpdate = true;
  }
  paint(null, 1);
  var shade = new THREE.TextureLoader().load(el.getAttribute('data-shade'));
  var mesh = null, aspect = 1;
  new THREE.GLTFLoader().load(el.getAttribute('data-model'), function (gl) {
    var src = null; gl.scene.traverse(function (o) { if (o.isMesh && !src) src = o; });
    var g = src.geometry, P = g.attributes.position, n = P.count;
    g.computeBoundingBox(); var bb = g.boundingBox, gW = bb.max.x - bb.min.x, gH = bb.max.y - bb.min.y;
    aspect = gW / gH;   // canvas is square; stretch the print so inches stay inches
    if (g.attributes.uv) g.setAttribute('uv2', g.attributes.uv.clone());
    var pl = new Float32Array(n * 2);
    for (var i = 0; i < n; i++) { pl[i * 2] = (P.getX(i) - bb.min.x) / gW; pl[i * 2 + 1] = 1 + (P.getY(i) - bb.max.y) / gH; }
    g.setAttribute('uv', new THREE.BufferAttribute(pl, 2));
    var idx = g.index.array, fr = [], bk = [], inner = [], a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
    var z0 = 0; for (i = 0; i < n; i++) z0 += P.getZ(i); z0 /= n;
    var nrm = new THREE.Vector3(), cen = new THREE.Vector3(), out = new THREE.Vector3();
    for (var t = 0; t < idx.length; t += 3) {
      a.fromBufferAttribute(P, idx[t]); b.fromBufferAttribute(P, idx[t + 1]); c.fromBufferAttribute(P, idx[t + 2]);
      nrm.copy(b).sub(a).cross(c.clone().sub(a)); cen.copy(a).add(b).add(c).multiplyScalar(1 / 3);
      out.set(cen.x, 0, cen.z - z0);
      var outward = nrm.dot(out) > 0;
      (outward ? (cen.z > z0 ? fr : bk) : inner).push(idx[t], idx[t + 1], idx[t + 2]);
    }
    g.setIndex(fr.concat(bk, inner)); g.clearGroups();
    g.addGroup(0, fr.length, 0); g.addGroup(fr.length, bk.length, 1); g.addGroup(fr.length + bk.length, inner.length, 2);
    var fab = { roughness: 0.95, metalness: 0, aoMap: shade, aoMapIntensity: 1.0 };
    var mFront = new THREE.MeshStandardMaterial(Object.assign({ map: frontTex }, fab));
    var mBack = new THREE.MeshStandardMaterial(Object.assign({ color: new THREE.Color(colour) }, fab));
    var mIn = new THREE.MeshStandardMaterial({ color: new THREE.Color(colour).multiplyScalar(0.72), roughness: 1, side: THREE.BackSide });
    mesh = new THREE.Mesh(g, [mFront, mBack, mIn]);
    mesh.position.set(-(bb.max.x + bb.min.x) / 2, -(bb.max.y + bb.min.y) / 2, -(bb.max.z + bb.min.z) / 2);
    scene.add(mesh);
    var dist = (gH / 2) / Math.tan((camera.fov / 2) * Math.PI / 180) * 1.18;
    camera.position.set(0, gH * 0.02, dist); camera.near = dist / 50; camera.far = dist * 10; camera.updateProjectionMatrix();
    controls.target.set(0, 0, 0); controls.update();
    if (artSrc) { var img = new Image(); img.onload = function () { paint(img, aspect); }; img.src = artSrc; }
    var lbl = el.querySelector('[data-tee3d-loading]'); if (lbl) lbl.remove();
  }, undefined, function () { var lbl = el.querySelector('[data-tee3d-loading]'); if (lbl) lbl.textContent = '3D did not load.'; });
  function tick() { requestAnimationFrame(tick); controls.update(); renderer.render(scene, camera); }
  tick();
  window.addEventListener('resize', function () { W = el.clientWidth; H = el.clientHeight || W; camera.aspect = W / H; camera.updateProjectionMatrix(); renderer.setSize(W, H); });
})();
