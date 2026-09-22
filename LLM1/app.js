/* ── State ──────────────────────────────────── */
        let chatAttachedImageBase64 = null;
        let logsChart = null;
        let actuatorMode = 'auto';

        // Persistent Client ID to keep chats isolated per browser
        let clientId = localStorage.getItem("orchid_client_id");
        if (!clientId) {
            clientId = "c_" + crypto.randomUUID().replace(/-/g, '').substring(0, 12);
            localStorage.setItem("orchid_client_id", clientId);
        }

        let currentSessionId = clientId + "_" + crypto.randomUUID();
        let chatHistory = [];
        let currentActuators = { exhaust_fan: 0, penyiraman_air: 0, penyiraman_pupuk: 0, mist_ruangan: 0 };

        /* ── Mobile Hamburger Menu Toggle ───────────── */

        function toggleChatSidebar() {
            const sidebar = document.getElementById('recentSidebar');
            if (sidebar) sidebar.classList.toggle('open');
        }

        function toggleMobileMenu(forceState) {
            const nav = document.getElementById('mainTabsNav');
            const btn = document.getElementById('mobileNavToggle');
            if (!nav || !btn) return;
            const isOpen = forceState !== undefined ? forceState : !nav.classList.contains('open');
            if (isOpen) {
                nav.classList.add('open');
                btn.classList.add('active');
            } else {
                nav.classList.remove('open');
                btn.classList.remove('active');
            }
        }

        /* ── Tab Switch ─────────────────────────────── */
        function switchTab(id) {
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));

            const targetTab = document.getElementById(id + '-tab');
            const targetBtn = document.getElementById('tabBtn-' + id);
            if (targetTab) {
                targetTab.classList.add('active');
                if (typeof gsap !== 'undefined') {
                    gsap.fromTo(targetTab, 
                        { opacity: 0, y: 15 }, 
                        { opacity: 1, y: 0, duration: 0.4, ease: "power2.out" }
                    );
                }
            }
            if (targetBtn) {
                targetBtn.classList.add('active');
                const mobileTitle = document.getElementById('mobileNavTitle');
                if (mobileTitle) mobileTitle.innerText = targetBtn.innerText.trim();
            }

            // Tutup burger menu di layar smartphone setelah memilih tab
            toggleMobileMenu(false);

            if (id === 'logger') fetchAndPopulateLogs();
        }


        /* ── Gauge Renderer ─────────────────────────── */
        function drawGauge(gId, vId, val, min, max, unit) {
            const pct = Math.min(Math.max((val - min) / (max - min), 0), 1);
            const arc = document.getElementById(gId);
            if (arc) arc.style.strokeDasharray = `${pct * 179} 239`;
            const el = document.getElementById(vId);
            if (el) el.innerText = val + unit;
        }

        function drawNPK(n, p, k) {
            document.getElementById('bN').style.width = Math.min(n / 300 * 100, 100) + '%';
            document.getElementById('bP').style.width = Math.min(p / 100 * 100, 100) + '%';
            document.getElementById('bK').style.width = Math.min(k / 300 * 100, 100) + '%';
            document.getElementById('dN').innerText = n + ' mg/kg';
            document.getElementById('dP').innerText = p + ' mg/kg';
            document.getElementById('dK').innerText = k + ' mg/kg';
        }

        /* ── Actuator Mode ──────────────────────────── */
        async function setActuatorMode(mode) {
            actuatorMode = mode;
            document.getElementById('btnModeAuto').classList.toggle('active', mode === 'auto');
            document.getElementById('btnModeManual').classList.toggle('active', mode === 'manual');
            document.getElementById('modeDesc').innerText = mode === 'auto'
                ? 'Mode otomatis aktif. Aktuator dikontrol AI berdasarkan data sensor secara real-time.'
                : 'Mode manual aktif. Anda bebas menyalakan/mematikan aktuator dengan sakelar berikut.';
            document.querySelectorAll('.actuator-switch').forEach(sw => sw.disabled = mode === 'auto');

            const payload = {
                Mode: mode === 'manual',
                Spray: currentActuators.mist_ruangan === 1,
                Murni: currentActuators.penyiraman_air === 1,
                Nutrisi: currentActuators.penyiraman_pupuk === 1,
                Fan: currentActuators.exhaust_fan === 1
            };
            try {
                await fetch('/control-actuator', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ device: 'mode_switch', state: mode === 'manual' ? 1 : 0, payload_data: payload })
                });
            } catch (err) {
                console.error("Gagal mengirim perubahan mode ke MQTT:", err);
            }

            if (mode === 'auto') {
                sendMetricsToBackend(false);
            }
        }

        async function toggleManualActuator(act, on) {
            if (actuatorMode !== 'manual') return;
            const state = on ? 1 : 0;
            currentActuators[act] = state;

            const map = {
                exhaust_fan: ['fanStatus', 'fanBox'],
                penyiraman_air: ['siramAirStatus', 'siramAirBox'],
                penyiraman_pupuk: ['pupukStatus', 'pupukBox'],
                mist_ruangan: ['mistRoomStatus', 'mistRoomBox']
            };
            updateActuatorUI(...map[act], state);

            try {
                const payload = {
                    Mode: true,
                    Spray: currentActuators.mist_ruangan === 1,
                    Murni: currentActuators.penyiraman_air === 1,
                    Nutrisi: currentActuators.penyiraman_pupuk === 1,
                    Fan: currentActuators.exhaust_fan === 1
                };
                await fetch('/control-actuator', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ device: act, state: state, payload_data: payload })
                });

                // Auto-off simulation di UI (3 detik) untuk penyiraman & mist
                if (state === 1 && act !== 'exhaust_fan') {
                    setTimeout(() => {
                        if (actuatorMode === 'manual') {
                            const sw = document.getElementById(act + 'Switch');
                            if (sw) sw.checked = false;
                            toggleManualActuator(act, false);
                        }
                    }, 3000);
                }
            } catch (err) {
                console.error("Gagal mengirim perintah ke MQTT:", err);
            }
        }

        function updateActuatorUI(badgeId, boxId, status) {
            const badge = document.getElementById(badgeId);
            const box = document.getElementById(boxId);
            if (!badge || !box) return;
            const isOn = status === 1;
            badge.innerText = isOn ? 'ON' : 'OFF';
            const isFan = badgeId.includes('fan');
            if (isOn) {
                badge.style.cssText = isFan
                    ? 'background:rgba(200,230,201,.95);color:#1b5e20;border-color:rgba(46,125,50,.3)'
                    : 'background:rgba(187,222,251,.95);color:#0277bd;border-color:rgba(2,119,189,.3)';
                box.className = 'actuator-card ' + (isFan ? 'on-fan' : 'on-mist');
            } else {
                badge.style.cssText = 'background:#f1f5f9;color:#64748b;border-color:#cbd5e1';
                box.className = 'actuator-card';
            }
        }

        /* ── File Upload / Image Attachment in Chat ── */
        function handleChatFileSelect(e) {
            const file = e.target.files && e.target.files[0];
            if (!file) return;
            if (!file.type.match('image.*')) {
                Swal.fire({icon: 'error', title: 'Oops...', text: 'Pilih file gambar yang valid (JPEG, PNG, atau WebP)'});
                return;
            }
            const reader = new FileReader();
            reader.onload = ev => {
                chatAttachedImageBase64 = ev.target.result;
                const previewBar = document.getElementById('chatAttachPreviewBar');
                const thumb = document.getElementById('chatAttachThumb');
                if (thumb) thumb.src = chatAttachedImageBase64;
                if (previewBar) previewBar.style.display = 'flex';
                const input = document.getElementById('chatInputField');
                if (input) input.focus();
            };
            reader.readAsDataURL(file);
        }

        function clearChatImageAttachment() {
            chatAttachedImageBase64 = null;
            const fileInput = document.getElementById('chatFileInput');
            if (fileInput) fileInput.value = '';
            const previewBar = document.getElementById('chatAttachPreviewBar');
            if (previewBar) previewBar.style.display = 'none';
            const thumb = document.getElementById('chatAttachThumb');
            if (thumb) thumb.src = '';
        }

        /* ── Markdown converter (simple) ───────────── */
        function fmtMD(t) {
            return t.replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        }

        /* ── Chat bubble helper & Typing Indicator ─── */
        function appendBubble(role, html, imageSrc = null) {
            const el = document.createElement('div');
            el.className = 'chat-bubble ' + (role === 'user' ? 'user' : 'ai');

            let contentHtml = '';
            if (imageSrc) {
                contentHtml += `<img src="${imageSrc}" class="chat-bubble-img" alt="Foto Anggrek Terlampir">`;
            }
            if (html) {
                const parsedHtml = (role === 'ai' && typeof marked !== 'undefined') ? marked.parse(html) : html;
                contentHtml += `<div class="chat-markdown-body">${parsedHtml}</div>`;
            }
            el.innerHTML = contentHtml;

            const msgs = document.getElementById('chatMessages');
            msgs.appendChild(el);
            msgs.scrollTop = msgs.scrollHeight;
        }

        function showTypingIndicator() {
            removeTypingIndicator();
            const msgs = document.getElementById('chatMessages');
            const typingEl = document.createElement('div');
            typingEl.className = 'typing-bubble';
            typingEl.id = 'aiTypingIndicator';
            typingEl.innerHTML = `
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
            `;
            msgs.appendChild(typingEl);
            msgs.scrollTop = msgs.scrollHeight;
        }

        function removeTypingIndicator() {
            const typingEl = document.getElementById('aiTypingIndicator');
            if (typingEl) typingEl.remove();
        }

        async function loadRecentChats() {
            const list = document.getElementById('recentChatsList');
            try {
                const res = await fetch('/recent-chats?client_id=' + encodeURIComponent(clientId));
                const data = await res.json();
                if (data.status === 'success' && Array.isArray(data.data)) {
                    list.innerHTML = '';
                    if (data.data.length === 0) {
                        list.innerHTML = '<div style="text-align:center; color:#94a3b8; font-size:0.85rem; margin-top:20px;">Belum ada riwayat</div>';
                        return;
                    }
                    data.data.forEach(chat => {
                        const div = document.createElement('div');
                        div.className = 'recent-item' + (chat.session_id === currentSessionId ? ' active' : '');

                        const titleSpan = document.createElement('span');
                        titleSpan.className = 'title';
                        titleSpan.innerText = chat.title || 'Percakapan';

                        const delBtn = document.createElement('button');
                        delBtn.className = 'chat-delete-btn';
                        delBtn.title = 'Hapus riwayat';
                        delBtn.innerHTML = '<i data-lucide="trash-2"></i>';
                        delBtn.onclick = (e) => {
                            e.stopPropagation();
                            deleteChatHistory(chat.session_id);
                        };

                        div.onclick = () => loadChatHistory(chat.session_id);
                        div.appendChild(titleSpan);
                        div.appendChild(delBtn);
                        list.appendChild(div);
                    });
                    lucide.createIcons();
                } else {
                    list.innerHTML = '<div style="text-align:center; color:#94a3b8; font-size:0.85rem; margin-top:20px;">Belum ada riwayat</div>';
                }
            } catch (e) {
                console.error("Error loading recent chats:", e);
                if (list) list.innerHTML = '<div style="text-align:center; color:#94a3b8; font-size:0.85rem; margin-top:20px;">Belum ada riwayat</div>';
            }
        }

        async function deleteChatHistory(sessionId) {
            const result = await Swal.fire({
                title: 'Yakin ingin menghapus?',
                text: "Riwayat chat ini tidak dapat dikembalikan!",
                icon: 'warning',
                showCancelButton: true,
                confirmButtonColor: '#ef4444',
                cancelButtonColor: '#94a3b8',
                confirmButtonText: 'Ya, hapus!'
            });
            if (!result.isConfirmed) return;
            try {
                const res = await fetch(`/chat-history/${sessionId}`, { method: 'DELETE' });
                const data = await res.json();
                if (data.status === 'success') {
                    if (currentSessionId === sessionId) {
                        resetChat();
                    } else {
                        loadRecentChats();
                    }
                } else {
                    Swal.fire('Gagal', data.detail || "Kesalahan server", 'error');
                }
            } catch (e) {
                console.error("Error deleting chat:", e);
                Swal.fire('Error', "Terjadi kesalahan saat menghapus chat.", 'error');
            }
        }

        async function loadChatHistory(sessionId) {
            currentSessionId = sessionId;
            chatHistory = [];
            clearChatImageAttachment();

            // Tandai item aktif di sidebar
            document.querySelectorAll('.recent-item').forEach(el => el.classList.remove('active'));
            loadRecentChats();

            document.getElementById('chatMessages').innerHTML = '<div style="text-align:center; color:#94a3b8; font-size:0.85rem; margin-top:20px;">Memuat riwayat chat...</div>';
            try {
                const res = await fetch(`/chat-history/${sessionId}`);
                const data = await res.json();
                if (data.status === 'success') {
                    document.getElementById('chatMessages').innerHTML = '';
                    if (!data.data || data.data.length === 0) {
                        resetChatUI();
                        return;
                    }
                    data.data.forEach(msg => {
                        appendBubble(msg.role === 'model' ? 'ai' : 'user', fmtMD(msg.message));
                        chatHistory.push({ role: msg.role, content: msg.message });
                    });
                } else {
                    resetChatUI();
                }
            } catch (e) {
                console.error("Error loading chat history:", e);
                resetChatUI();
            }
        }

        function createNewChat() {
            currentSessionId = clientId + "_" + crypto.randomUUID();
            chatHistory = [];
            clearChatImageAttachment();
            resetChatUI();
            loadRecentChats();
            const input = document.getElementById('chatInputField');
            if (input) input.focus();
        }

        function resetChatUI() {
            document.getElementById('chatMessages').innerHTML = `
                <div class="chat-bubble ai">
                    Halo! Saya <b>Dokter Anggrek AI</b> <i data-lucide="flower"></i><br><br>
                    Saya siap membantu Anda dalam:<br>
                    • Diagnosis penyakit & hama anggrek via foto<br>
                    • Perawatan, penyiraman, dan pemupukan<br>
                    • Tips media tanam & pencegahan hama<br>
                    • Konsultasi anggrek lainnya<br><br>
                    Ketik pertanyaan atau klik ikon <b><i data-lucide="paperclip"></i> Foto</b> untuk melampirkan gambar anggrek Anda! <i data-lucide="stethoscope"></i>
                </div>`;
            clearChatImageAttachment();
        }

        async function sendChatMessage() {
            const input = document.getElementById('chatInputField');
            const btn = document.getElementById('chatSendBtn');
            const attachBtn = document.getElementById('chatAttachBtn');
            const msg = input.value.trim();
            const attachedImg = chatAttachedImageBase64;

            // Jika tidak ada teks maupun gambar terlampir, jangan kirim apa-apa
            if (!msg && !attachedImg) return;

            // Tampilkan bubble user di antarmuka
            appendBubble('user', msg || '<i>[Melampirkan foto anggrek untuk dianalisis]</i>', attachedImg);

            // Bersihkan input dan pratinjau lampiran
            input.value = '';
            clearChatImageAttachment();

            // Kunci input saat menunggu respon
            input.disabled = true;
            btn.disabled = true;
            if (attachBtn) attachBtn.disabled = true;
            btn.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';
            showTypingIndicator();

            try {
                const res = await fetch('/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: currentSessionId,
                        message: msg,
                        image: attachedImg,
                        history: chatHistory
                    })
                });
                const data = await res.json();
                removeTypingIndicator();
                if (!res.ok) throw new Error(data.detail || 'Error server');
                
                const responseText = data.response;
                const el = document.createElement('div');
                el.className = 'chat-bubble ai chat-markdown-body';
                const msgs = document.getElementById('chatMessages');
                msgs.appendChild(el);
                
                // Frontend Typewriter Effect
                let i = 0;
                let currentText = "";
                const typeInterval = setInterval(() => {
                    currentText += responseText.charAt(i);
                    el.innerHTML = (typeof marked !== 'undefined') ? marked.parse(currentText) : currentText;
                    msgs.scrollTop = msgs.scrollHeight;
                    i++;
                    if (i >= responseText.length) {
                        clearInterval(typeInterval);
                    }
                }, 10); // 10ms per char is very fast and smooth

                const historyUserMsg = msg ? (attachedImg ? `${msg} [Foto terlampir]` : msg) : '[Melampirkan foto anggrek]';
                chatHistory.push({ role: 'user', content: historyUserMsg });
                chatHistory.push({ role: 'model', content: responseText });
                loadRecentChats(); // Refresh daftar riwayat chat di sidebar
            } catch (err) {
                removeTypingIndicator();
                appendBubble('ai', '<i data-lucide="alert-triangle"></i> Gagal mendapatkan respon: ' + err.message);
            } finally {
                input.disabled = false;
                btn.disabled = false;
                if (attachBtn) attachBtn.disabled = false;
                btn.innerHTML = '<i data-lucide="send-horizontal"></i>'; lucide.createIcons();
                input.focus();
            }
        }

        async function resetChat() {
            const result = await Swal.fire({
                title: 'Mulai obrolan baru?',
                icon: 'question',
                showCancelButton: true,
                confirmButtonColor: '#2e7d32',
                confirmButtonText: 'Ya, mulai'
            });
            if (!result.isConfirmed) return;
            createNewChat();
        }

        /* ── Metrics to Backend ─────────────────────── */
        async function sendMetricsToBackend(redirect = true) {
            const vals = {
                air_temperature: parseFloat(document.getElementById('simAirTemp').value),
                air_humidity: parseFloat(document.getElementById('simAirHumid').value),
                lux: parseFloat(document.getElementById('simLux').value),
                tds: parseFloat(document.getElementById('simTDS').value),
                meja1: {
                    suhu: parseFloat(document.getElementById('simM1Suhu').value),
                    kelembapan: parseFloat(document.getElementById('simM1Humid').value),
                    ec: parseFloat(document.getElementById('simM1EC').value),
                    ph: parseFloat(document.getElementById('simM1pH').value)
                },
                meja2: {
                    suhu: parseFloat(document.getElementById('simM2Suhu').value),
                    kelembapan: parseFloat(document.getElementById('simM2Humid').value),
                    ec: parseFloat(document.getElementById('simM2EC').value),
                    ph: parseFloat(document.getElementById('simM2pH').value)
                },
                meja3: {
                    suhu: parseFloat(document.getElementById('simM3Suhu').value),
                    kelembapan: parseFloat(document.getElementById('simM3Humid').value),
                    ec: parseFloat(document.getElementById('simM3EC').value),
                    ph: parseFloat(document.getElementById('simM3pH').value)
                }
            };
            const loader = document.getElementById('greenhouseLoader');
            const btn = document.getElementById('analyzeBtn');
            loader.style.display = 'block'; btn.disabled = true;

            const payload = { ...vals, mode: actuatorMode, manual_actions: actuatorMode === 'manual' ? currentActuators : null };

            try {
                const res = await fetch('/analyze-metrics', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Error');

                // Update UI manually immediately (will also be polled by fetchRealTimeTelemetry later)
                updateGauge('cAirTemp', 'vAirTemp', vals.air_temperature, 15, 45, '°C');
                updateGauge('cAirHumid', 'vAirHumid', vals.air_humidity, 20, 100, '%');
                let iklimStatEl = document.getElementById('iklimStatusText');
                if (iklimStatEl) {
                    if (vals.air_temperature >= 20 && vals.air_temperature <= 30 && vals.air_humidity >= 50 && vals.air_humidity <= 85) {
                        iklimStatEl.innerText = 'Optimal';
                    } else if (vals.air_temperature > 30) {
                        iklimStatEl.innerText = 'Terlalu Panas';
                    } else {
                        iklimStatEl.innerText = 'Tidak Ideal';
                    }
                }
                updateGauge('cTDS', 'vTDS', vals.tds, 0, 600, '');
                if (document.getElementById('tdsStatusText')) document.getElementById('tdsStatusText').innerText = vals.tds < 100 ? 'Rendah' : (vals.tds > 400 ? 'Tinggi' : 'Optimal');


                updateGauge('cLuxGauge', 'vLux', vals.lux, 0, 10000, '');
                if (document.getElementById('luxStatusText')) document.getElementById('luxStatusText').innerText = vals.lux < 2000 ? 'Redup' : (vals.lux > 8000 ? 'Terik' : 'Optimal');

                setMetricText('vM1Suhu', vals.meja1.suhu, '°C');
                setMetricText('vM1Humid', vals.meja1.kelembapan, '%');
                updateGauge('cM1EC', 'vM1EC', vals.meja1.ec, 0, 15, '');
                updateGauge('cM1pH', 'vM1pH', vals.meja1.ph, 0, 14, '');

                setMetricText('vM2Suhu', vals.meja2.suhu, '°C');
                setMetricText('vM2Humid', vals.meja2.kelembapan, '%');
                updateGauge('cM2EC', 'vM2EC', vals.meja2.ec, 0, 15, '');
                updateGauge('cM2pH', 'vM2pH', vals.meja2.ph, 0, 14, '');

                setMetricText('vM3Suhu', vals.meja3.suhu, '°C');
                setMetricText('vM3Humid', vals.meja3.kelembapan, '%');
                updateGauge('cM3EC', 'vM3EC', vals.meja3.ec, 0, 15, '');
                updateGauge('cM3pH', 'vM3pH', vals.meja3.ph, 0, 14, '');

                // AI summary
                document.getElementById('resAir').innerText = data.status_udara || '—';
                document.getElementById('resSoil').innerText = data.status_tanah || '—';
                document.getElementById('resTDS').innerText = data.status_nutrisi || '—';
                document.getElementById('resSolar').innerText = data.status_cahaya || '—';
                document.getElementById('resRec').innerHTML = fmtMD(data.rekomendasi || '');

                // Actuators (auto)
                if (actuatorMode === 'auto') {
                    currentActuators = { ...data.actions };
                    const autoOffDevices = ['penyiraman_air', 'penyiraman_pupuk', 'mist_ruangan'];
                    ['exhaust_fan', ...autoOffDevices].forEach(k => {
                        const sw = document.getElementById(k + 'Switch');
                        if (sw) sw.checked = data.actions[k] === 1;
                    });

                    updateActuatorUI('fanStatus', 'fanBox', data.actions.exhaust_fan);
                    updateActuatorUI('siramAirStatus', 'siramAirBox', data.actions.penyiraman_air);
                    updateActuatorUI('pupukStatus', 'pupukBox', data.actions.penyiraman_pupuk);
                    updateActuatorUI('mistRoomStatus', 'mistRoomBox', data.actions.mist_ruangan);

                    // Auto-off simulation di UI (3 detik) untuk mode Auto
                    setTimeout(() => {
                        if (actuatorMode === 'auto') {
                            autoOffDevices.forEach(device => {
                                if (data.actions[device] === 1) {
                                    currentActuators[device] = 0;
                                    const sw = document.getElementById(device + 'Switch');
                                    if (sw) sw.checked = false;
                                }
                            });

                            if (data.actions.penyiraman_air === 1) updateActuatorUI('siramAirStatus', 'siramAirBox', 0);
                            if (data.actions.penyiraman_pupuk === 1) updateActuatorUI('pupukStatus', 'pupukBox', 0);
                            if (data.actions.mist_ruangan === 1) updateActuatorUI('mistRoomStatus', 'mistRoomBox', 0);
                        }
                    }, 3000);
                }
                if (redirect) switchTab('greenhouse');
            } catch (err) {
                alert('Gagal menganalisis: ' + err.message);
            } finally {
                loader.style.display = 'none'; btn.disabled = false;
            }
        }

        /* ── Logger ─────────────────────────────────── */
        async function fetchAndPopulateLogs() {
            const tbody = document.getElementById('logsTableBody');
            tbody.innerHTML = Array(5).fill('<tr>' + Array(12).fill('<td><div class="skeleton" style="height: 20px; width: 100%;"></div></td>').join('') + '</tr>').join('');
            try {
                const res = await fetch('/get-logs');
                const data = await res.json();
                if (!res.ok) throw new Error();
                const logs = data.logs;
                tbody.innerHTML = '';
                [...logs].reverse().forEach((log, idx) => {
                    const tr = document.createElement('tr');
                    tr.style.opacity = 0;
                    tr.style.transform = 'translateY(10px)';
                    const actions = log.actions || {
                        exhaust_fan: '-',
                        penyiraman_air: '-',
                        penyiraman_pupuk: '-',
                        mist_ruangan: '-'
                    };
                    const onColor = (v, c) => v === 1 ? `color:${c};font-weight:bold` : ''
                    tr.innerHTML = `
                <td><b>${log.timestamp || '-'}</b></td>
                <td>${log.air_temperature != null ? log.air_temperature + '°C' : '-'}</td>
                <td>${log.air_humidity != null ? log.air_humidity + '%' : '-'}</td>
                <td>${log.lux != null ? log.lux + ' Lux' : '-'}</td>
                <td>${log.tds != null ? log.tds + ' ppm' : '-'}</td>
                <td>${log.meja1?.kelembapan != null ? log.meja1.kelembapan + '%' : '-'}</td>
                <td>${log.meja2?.kelembapan != null ? log.meja2.kelembapan + '%' : '-'}</td>
                <td>${log.meja3?.kelembapan != null ? log.meja3.kelembapan + '%' : '-'}</td>
                <td><span style="${onColor(actions.exhaust_fan, 'var(--primary)')}">${actions.exhaust_fan}</span></td>
                <td><span style="${onColor(actions.penyiraman_air, 'var(--info)')}">${actions.penyiraman_air}</span></td>
                <td><span style="${onColor(actions.penyiraman_pupuk, 'var(--accent)')}">${actions.penyiraman_pupuk}</span></td>
                <td><span style="${onColor(actions.mist_ruangan, 'var(--info)')}">${actions.mist_ruangan}</span></td>`;
                    tbody.appendChild(tr);
                    
                    if (typeof gsap !== 'undefined') {
                        gsap.to(tr, { opacity: 1, y: 0, duration: 0.3, delay: idx * 0.05, ease: "power2.out" });
                    } else {
                        tr.style.opacity = 1;
                        tr.style.transform = 'none';
                    }
                });

                const labels = logs.map(l => l.timestamp.includes(' ') ? l.timestamp.split(' ')[1] : l.timestamp);
                
                const commonOptions = {
                    chart: { height: 250, type: 'area', fontFamily: 'Inter, sans-serif', toolbar: { show: false } },
                    dataLabels: { enabled: false },
                    stroke: { curve: 'smooth', width: 2 },
                    fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.4, opacityTo: 0.05, stops: [0, 100] } },
                    xaxis: { categories: labels, labels: { style: { colors: '#94a3b8' } }, axisBorder: { show: false }, axisTicks: { show: false } },
                    legend: { position: 'top', horizontalAlign: 'center' },
                    tooltip: { theme: 'light' }
                };

                // Helper function to render a chart safely
                const renderChart = (selector, series, yaxisOptions = {}, extraOpt = {}) => {
                    const el = document.querySelector(selector);
                    if (!el) return;
                    if (el._chart) { el._chart.destroy(); }
                    
                    const opt = { ...commonOptions, series, yaxis: yaxisOptions, ...extraOpt };
                    el._chart = new ApexCharts(el, opt);
                    el._chart.render();
                };

                // 1. Suhu Tanah
                renderChart('#chartSuhuTanah', [
                    { name: 'Meja 1 (°C)', data: logs.map(l => l.meja1?.suhu || 0) },
                    { name: 'Meja 2 (°C)', data: logs.map(l => l.meja2?.suhu || 0) },
                    { name: 'Meja 3 (°C)', data: logs.map(l => l.meja3?.suhu || 0) }
                ], { labels: { style: { colors: '#94a3b8' } } });

                // 2. Kelembapan Tanah
                renderChart('#chartHumidTanah', [
                    { name: 'Meja 1 (%)', data: logs.map(l => l.meja1?.kelembapan || 0) },
                    { name: 'Meja 2 (%)', data: logs.map(l => l.meja2?.kelembapan || 0) },
                    { name: 'Meja 3 (%)', data: logs.map(l => l.meja3?.kelembapan || 0) }
                ], { labels: { style: { colors: '#94a3b8' } } });

                // 3. EC Tanah
                renderChart('#chartECTanah', [
                    { name: 'Meja 1 (mS/cm)', data: logs.map(l => l.meja1?.ec || 0) },
                    { name: 'Meja 2 (mS/cm)', data: logs.map(l => l.meja2?.ec || 0) },
                    { name: 'Meja 3 (mS/cm)', data: logs.map(l => l.meja3?.ec || 0) }
                ], { labels: { style: { colors: '#94a3b8' } } });

                // 4. Perbandingan Suhu & Kelembapan (Meja 1)
                renderChart('#chartBandingTanah', [
                    { name: 'Suhu M1 (°C)', type: 'area', data: logs.map(l => l.meja1?.suhu || 0) },
                    { name: 'Humid M1 (%)', type: 'bar', data: logs.map(l => l.meja1?.kelembapan || 0) }
                ], [
                    { seriesName: 'Suhu M1 (°C)', title: { text: 'Suhu (°C)' }, labels: { style: { colors: '#f59e0b' } } },
                    { seriesName: 'Humid M1 (%)', opposite: true, title: { text: 'Kelembapan (%)' }, labels: { style: { colors: '#0ea5e9' } } }
                ], { chart: { type: 'line', height: 250, toolbar: { show: false } }, stroke: { width: [2, 0] }, fill: { type: ['gradient', 'solid'] } });

                // 5. Udara
                renderChart('#chartUdara', [
                    { name: 'Suhu Udara (°C)', type: 'area', data: logs.map(l => l.air_temperature || 0) },
                    { name: 'Humid Udara (%)', type: 'bar', data: logs.map(l => l.air_humidity || 0) }
                ], [
                    { seriesName: 'Suhu Udara (°C)', title: { text: 'Suhu (°C)' }, labels: { style: { colors: '#f97316' } } },
                    { seriesName: 'Humid Udara (%)', opposite: true, title: { text: 'Kelembapan (%)' }, labels: { style: { colors: '#06b6d4' } } }
                ], { chart: { type: 'line', height: 250, toolbar: { show: false } }, stroke: { width: [2, 0] }, fill: { type: ['gradient', 'solid'] } });
} catch (e) { console.error('Logger error:', e); }
        }

        function unlockSecretConfig() {
            const btn = document.getElementById('tabBtn-simconfig');
            if (btn.style.display === 'none') {
                btn.style.display = 'inline-block';
                switchTab('simconfig');
            } else {
                btn.style.display = 'none';
                switchTab('greenhouse');
            }
        }

        async function sendThresholdsToPLC() {
            const loader = document.getElementById('greenhouseLoader');
            loader.classList.add('active');

            const payloadSensor = {
                Suhu_Siang: parseFloat(document.getElementById('spSuhuSiang').value) || 0,
                Suhu_Malam: parseFloat(document.getElementById('spSuhuMalam').value) || 0,
                Hum_low: parseFloat(document.getElementById('spHumLow').value) || 0,
                TDS_Sp: parseFloat(document.getElementById('spTDSSp').value) || 0,
                Soil_Temp: parseFloat(document.getElementById('spSoilTemp').value) || 0,
                Soil_moist: parseFloat(document.getElementById('spSoilMoist').value) || 0
            };

            const payloadDurasi = {
                mist_on: parseInt(document.getElementById('spMistOn').value) || 0,
                mist_off: parseInt(document.getElementById('spMistOff').value) || 0,
                murni_on: parseInt(document.getElementById('spMurniOn').value) || 0,
                murni_off: parseInt(document.getElementById('spMurniOff').value) || 0,
                nutrisi_on: parseInt(document.getElementById('spNutrisiOn').value) || 0,
                nutrisi_off: parseInt(document.getElementById('spNutrisiOff').value) || 0
            };

            const payloadNutrisi = {
                Senin: document.getElementById('spSenin').checked,
                Selasa: document.getElementById('spSelasa').checked,
                Rabu: document.getElementById('spRabu').checked,
                Kamis: document.getElementById('spKamis').checked,
                Jumat: document.getElementById('spJumat').checked,
                Sabtu: document.getElementById('spSabtu').checked,
                Minggu: document.getElementById('spMinggu').checked,
                Jam: parseInt(document.getElementById('spJamNutrisi').value) || 0
            };

            try {
                const res1 = await fetch('/setpoint/sensor', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payloadSensor)
                });
                const res2 = await fetch('/setpoint/durasi', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payloadDurasi)
                });
                const res3 = await fetch('/setpoint/nutrisi', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payloadNutrisi)
                });

                if (res1.ok && res2.ok && res3.ok) {
                    Swal.fire('Berhasil', 'Semua setpoint berhasil dikirim ke PLC via MQTT!', 'success');
                } else {
                    Swal.fire('Gagal', 'Gagal mengirim salah satu atau lebih setpoint. Periksa log backend.', 'error');
                }
            } catch (e) {
                Swal.fire('Error Jaringan', e.message, 'error');
            } finally {
                loader.classList.remove('active');
            }
        }

        /* ── Gauge & Meter Helpers ─────────────────── */
        const GAUGE_CIRCUMFERENCE = 201.06; // 2 * PI * 32

        function setMetricText(id, value, unit) {
            const el = document.getElementById(id);
            if (el) {
                const num = parseFloat(value);
                if (!isNaN(num)) {
                    const formatted = (num % 1 !== 0) ? num.toFixed(1) : num;
                    el.innerText = formatted + (unit || '');
                } else {
                    el.innerText = value + (unit || '');
                }
            }
        }

        function updateGauge(circleId, textId, value, min, max, unit) {
            const circle = document.getElementById(circleId);
            const textEl = document.getElementById(textId);
            const num = parseFloat(value);

            if (textEl) {
                if (!isNaN(num)) {
                    if (typeof gsap !== 'undefined') {
                        const currentVal = parseFloat(textEl.innerText) || 0;
                        const targetObj = { val: currentVal };
                        gsap.to(targetObj, {
                            val: num,
                            duration: 1.2,
                            ease: "power2.out",
                            onUpdate: function() {
                                const current = targetObj.val;
                                const formatted = (num % 1 !== 0) ? current.toFixed(2) : Math.round(current);
                                textEl.innerText = formatted + (unit || '');
                            }
                        });
                    } else {
                        const formatted = (num % 1 !== 0) ? num.toFixed(2) : num;
                        textEl.innerText = formatted + (unit || '');
                    }
                } else {
                    textEl.innerText = value;
                }
            }

            if (circle && !isNaN(num)) {
                const clamped = Math.min(Math.max(num, min), max);
                const percent = (clamped - min) / (max - min);
                const strokeDash = (percent * GAUGE_CIRCUMFERENCE).toFixed(1);
                circle.style.strokeDasharray = `${strokeDash} ${GAUGE_CIRCUMFERENCE}`;
            }
        }

        function updateBar(barId, value, min, max) {
            const bar = document.getElementById(barId);
            if (bar) {
                const num = parseFloat(value) || 0;
                const clamped = Math.min(Math.max(num, min), max);
                const pct = Math.round(((clamped - min) / (max - min)) * 100);
                bar.style.width = pct + '%';
            }
        }

        window.addEventListener('DOMContentLoaded', () => {
            // Render recent chats
            loadRecentChats();

            // Inisialisasi awal nilai gauge
            updateGauge('cAirTemp', 'vAirTemp', 25.0, 15, 45, '°C');
            updateGauge('cAirHumid', 'vAirHumid', 74, 20, 100, '%');
            updateGauge('cLuxGauge', 'vLux', 4500, 0, 10000, '');

            updateGauge('cTDS', 'vTDS', 210, 0, 600, '');

            // Default Meja 1 (Suhu & Moisture text, EC & pH gauge)
            setMetricText('vM1Suhu', 23.5, '°C');
            setMetricText('vM1Humid', 71, '%');
            updateGauge('cM1EC', 'vM1EC', 1.20, 0, 15, '');
            updateGauge('cM1pH', 'vM1pH', 6.5, 0, 14, '');

            // Default Meja 2
            setMetricText('vM2Suhu', 23.8, '°C');
            setMetricText('vM2Humid', 68, '%');
            updateGauge('cM2EC', 'vM2EC', 1.10, 0, 15, '');
            updateGauge('cM2pH', 'vM2pH', 6.2, 0, 14, '');

            // Default Meja 3
            setMetricText('vM3Suhu', 24.1, '°C');
            setMetricText('vM3Humid', 75, '%');
            updateGauge('cM3EC', 'vM3EC', 1.40, 0, 15, '');
            updateGauge('cM3pH', 'vM3pH', 6.7, 0, 14, '');

            // Polling telemetry real-time
            setInterval(fetchRealTimeTelemetry, 30000);

            // Cuaca awal dan berkala
            fetchAndPopulateLogs();
            fetchWeather();
            setInterval(fetchWeather, 600000);
        });

                async function fetchWeather() {
            try {
                // Gunakan lokasi tetap (Bandung) untuk Greenhouse IoT (Lebih cepat & tidak di-block AdBlocker)
                const lat = -6.9147;
                const lon = 107.6098;
                
                const res = await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&current=temperature_2m,relative_humidity_2m,wind_speed_10m`);
                if (res.ok) {
                    const data = await res.json();
                    const current = data.current;
                    document.getElementById('wTemp').innerHTML = '<i data-lucide="thermometer"></i> ' + current.temperature_2m + '&deg;C';
                    document.getElementById('wWind').innerHTML = '<i data-lucide="wind"></i> ' + current.wind_speed_10m + ' km/h';
                    document.getElementById('wHumid').innerHTML = '<i data-lucide="droplet"></i> ' + current.relative_humidity_2m + '%';
                    if (typeof lucide !== 'undefined') lucide.createIcons();
                } else {
                    console.error("Open-Meteo Error:", res.status);
                    document.getElementById('wTemp').innerHTML = '<i data-lucide="alert-triangle"></i> Err';
                }
            } catch (e) {
                console.error("Gagal mengambil data cuaca", e);
                document.getElementById('wTemp').innerHTML = '<i data-lucide="wifi-off"></i> Err';
            }
        }

        async function fetchRealTimeTelemetry() {
            try {
                const res = await fetch('/latest-telemetry');
                if (res.ok) {
                    const data = await res.json();

                    // Cek status koneksi PLC (selisih waktu dalam detik, batas 15s)
                    const nowSec = Date.now() / 1000;
                    const lastUpdate = data.last_update || 0;
                    const isOnline = (nowSec - lastUpdate) < 15;
                    const plcEl = document.getElementById('plcStatus');
                    const plcText = document.getElementById('plcStatusText');

                    if (plcEl && plcText) {
                        if (isOnline) {
                            plcEl.className = 'plc-status online';
                            plcText.innerText = 'PLC Online';
                        } else {
                            plcEl.className = 'plc-status offline';
                            plcText.innerText = 'PLC Offline';
                        }
                    }

                    // Lingkungan
                    updateGauge('cAirTemp', 'vAirTemp', data.air_temperature, 15, 45, '°C');
                    updateGauge('cAirHumid', 'vAirHumid', data.air_humidity, 20, 100, '%');
                    let iklimStat = document.getElementById('iklimStatusText');
                    if (iklimStat) {
                        if (data.air_temperature >= 20 && data.air_temperature <= 30 && data.air_humidity >= 50 && data.air_humidity <= 85) {
                            iklimStat.innerText = 'Optimal';
                        } else if (data.air_temperature > 30) {
                            iklimStat.innerText = 'Terlalu Panas';
                        } else {
                            iklimStat.innerText = 'Tidak Ideal';
                        }
                    }
                    const luxVal = data.lux !== undefined ? data.lux : (data.solar || 4500);

                    updateGauge('cLuxGauge', 'vLux', luxVal, 0, 10000, '');
                    if (document.getElementById('luxStatusText')) document.getElementById('luxStatusText').innerText = luxVal < 2000 ? 'Redup' : (luxVal > 8000 ? 'Terik' : 'Optimal');

                    // Air
                    updateGauge('cTDS', 'vTDS', data.tds || 210, 0, 600, '');
                    let tdsVal = data.tds || 210;
                    if (document.getElementById('tdsStatusText')) document.getElementById('tdsStatusText').innerText = tdsVal < 100 ? 'Rendah' : (tdsVal > 400 ? 'Tinggi' : 'Optimal');

                    // Meja 1
                    if (data.meja1) {
                        setMetricText('vM1Suhu', data.meja1.suhu, '°C');
                        setMetricText('vM1Humid', data.meja1.kelembapan, '%');
                        updateGauge('cM1EC', 'vM1EC', data.meja1.ec, 0, 15, '');
                        updateGauge('cM1pH', 'vM1pH', data.meja1.ph, 0, 14, '');
                    }

                    // Meja 2
                    if (data.meja2) {
                        setMetricText('vM2Suhu', data.meja2.suhu, '°C');
                        setMetricText('vM2Humid', data.meja2.kelembapan, '%');
                        updateGauge('cM2EC', 'vM2EC', data.meja2.ec, 0, 15, '');
                        updateGauge('cM2pH', 'vM2pH', data.meja2.ph, 0, 14, '');
                    }

                    // Meja 3
                    if (data.meja3) {
                        setMetricText('vM3Suhu', data.meja3.suhu, '°C');
                        setMetricText('vM3Humid', data.meja3.kelembapan, '%');
                        updateGauge('cM3EC', 'vM3EC', data.meja3.ec, 0, 15, '');
                        updateGauge('cM3pH', 'vM3pH', data.meja3.ph, 0, 14, '');
                    }
                }
            } catch (e) {
                console.error("Gagal mengambil telemetry real-time", e);
            }
        }

        /* ─── MAC DOCK MAGNIFICATION LOGIC ─── */
        const macDock = document.getElementById('macDock');
        const dockItems = macDock ? macDock.querySelectorAll('.dock-item') : [];
        const maxScale = 1.4;
        const proximity = 120; // Radius sensor kursor

        if (macDock && typeof gsap !== 'undefined') {
            let isTicking = false;
            macDock.addEventListener('mousemove', (e) => {
                if (!isTicking) {
                    window.requestAnimationFrame(() => {
                        const mouseX = e.clientX;
                        dockItems.forEach(item => {
                            const rect = item.getBoundingClientRect();
                            const itemCenterX = rect.left + rect.width / 2;
                            const distance = Math.abs(mouseX - itemCenterX);
                            
                            let scale = 1;
                            if (distance < proximity) {
                                scale = 1 + (maxScale - 1) * Math.cos((distance / proximity) * (Math.PI / 2));
                            }
                            
                            gsap.to(item, {
                                width: 48 * scale,
                                height: 48 * scale,
                                marginBottom: (48 * scale - 48) / 2,
                                duration: 0.1,
                                ease: "power2.out"
                            });
                            
                            const svg = item.querySelector('svg');
                            if (svg) {
                                gsap.to(svg, {
                                    width: 20 * scale,
                                    height: 20 * scale,
                                    duration: 0.1
                                });
                            }
                        });
                        isTicking = false;
                    });
                    isTicking = true;
                }
            });

            macDock.addEventListener('mouseleave', () => {
                dockItems.forEach(item => {
                    gsap.to(item, {
                        width: 48,
                        height: 48,
                        marginBottom: 0,
                        duration: 0.4,
                        ease: "elastic.out(1, 0.4)"
                    });
                    const svg = item.querySelector('svg');
                    if (svg) {
                        gsap.to(svg, {
                            width: 20,
                            height: 20,
                            duration: 0.4,
                            ease: "elastic.out(1, 0.4)"
                        });
                    }
                });
            });
        }

        /* Initialize Lucide Icons */
        lucide.createIcons();

/* Dark Mode Logic */
function applyDarkMode(isDark) {
    const root = document.documentElement;
    const icon = document.getElementById('darkModeIcon');
    if (isDark) {
        root.classList.add('dark-theme');
        if(icon) icon.setAttribute('data-lucide', 'sun');
    } else {
        root.classList.remove('dark-theme');
        if(icon) icon.setAttribute('data-lucide', 'moon');
    }
    if (typeof lucide !== 'undefined') lucide.createIcons();
}

function toggleDarkMode() {
    const root = document.documentElement;
    const isDark = !root.classList.contains('dark-theme');
    localStorage.setItem('orchid_dark_mode', isDark);
    applyDarkMode(isDark);
}

// Initial Apply
if (localStorage.getItem('orchid_dark_mode') === 'true') {
    applyDarkMode(true);
}
