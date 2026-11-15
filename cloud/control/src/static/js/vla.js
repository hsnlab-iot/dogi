const socket = io({ path: '/apps/vla/socket.io/' });
const promptInput = document.getElementById('prompt-input');
const sendButton = document.getElementById('prompt-send');
const stopButton = document.getElementById('prompt-abort');
const newButton = document.getElementById('prompt-new');
const errorText = document.getElementById('vla-error');
const video = document.getElementById('video-stream');
const steeringForm = document.getElementById('steering-form');
const steeringFields = steeringForm.elements;
const applyButton = document.getElementById('steering-apply');
const pathLine = document.getElementById('path-line');
const pathWaypoint = document.getElementById('path-waypoint');
const pitch = document.getElementById('camera-pitch');
const pitchValue = document.getElementById('pitch-value');
const pitchApply = document.getElementById('pitch-apply');
const pitchCenter = document.getElementById('pitch-center');
const manualForm = document.getElementById('manual-form');
const manualRun = document.getElementById('manual-run');
const manualStop = document.getElementById('manual-stop');
let appliedPitch = null;
let applied = '';
let available = false;
let ready = false;
let pending = 0;

function updateButtons() {
    sendButton.disabled = !ready || pending > 0 || !promptInput.value.trim();
    stopButton.disabled = !available;
    newButton.disabled = !available;
    applyButton.disabled = !ready || pending > 0;
    pitchApply.disabled = pitchCenter.disabled = !available || pending > 0;
    manualRun.disabled = !ready || pending > 0;
    manualStop.disabled = !available;
}
function command(event, data) {
    pending += 1;
    updateButtons();
    errorText.textContent = '';
    socket.timeout(4000).emit(event, data, function(error, reply) {
        pending -= 1;
        if (error || !reply || !reply.ok) {
            errorText.textContent = error ? 'Command timed out; check the worker.' :
                ((reply && reply.error) || 'Command failed');
        }
        updateButtons();
    });
}
sendButton.onclick = function() { command('prompt', { prompt: promptInput.value }); };
stopButton.onclick = function() { command('abort_prompt', null); };
newButton.onclick = function() { promptInput.value = ''; command('new', null); };
manualForm.onsubmit = function(event) {
    event.preventDefault();
    const fields = manualForm.elements;
    command('manual_move', {
        vx: fields.vx.valueAsNumber, vy: fields.vy.valueAsNumber,
        yaw: fields.yaw.valueAsNumber, duration: fields.duration.valueAsNumber / 1000
    });
};
manualStop.onclick = function() { command('abort_prompt', null); };
pitch.oninput = function() { pitchValue.textContent = pitch.value + '°'; };
document.getElementById('camera-form').onsubmit = function(event) {
    event.preventDefault();
    command('camera_pitch', pitch.valueAsNumber);
};
pitchCenter.onclick = function() {
    pitch.value = 0;
    pitch.oninput();
    command('camera_pitch', 0);
};
steeringForm.onsubmit = function(event) {
    event.preventDefault();
    command('steering', {
        cone_degrees: steeringFields.cone_degrees.valueAsNumber,
        forward_duration: steeringFields.forward_duration.valueAsNumber / 1000,
        turn_duration: steeringFields.turn_duration.valueAsNumber / 1000,
        invert_yaw: steeringFields.invert_yaw.checked,
        settle_duration: steeringFields.settle_duration.valueAsNumber / 1000
    });
};
function renderSteering(settings, decision) {
    const serialized = JSON.stringify(settings);
    if (settings && serialized !== applied) {
        applied = serialized;
        steeringFields.cone_degrees.value = settings.cone_degrees;
        steeringFields.forward_duration.value = Math.round(settings.forward_duration * 1000);
        steeringFields.turn_duration.value = Math.round(settings.turn_duration * 1000);
        steeringFields.invert_yaw.checked = settings.invert_yaw === true;
        steeringFields.settle_duration.value = Math.round((settings.settle_duration ?? 0.6) * 1000);
    }
    const cone = document.getElementById('forward-cone');
    if (settings) {
        const angle = settings.cone_degrees * Math.PI / 180;
        const dx = 90 * Math.sin(angle);
        const y = 110 - 90 * Math.cos(angle);
        cone.setAttribute('d', `M100 110 L${100 - dx} ${y} A90 90 0 0 1 ${100 + dx} ${y} Z`);
    } else {
        cone.removeAttribute('d');
    }
    document.getElementById('steering-active').textContent = settings ?
        'Forward cone ±' + settings.cone_degrees + '° · yaw ' +
        Math.round(settings.forward_duration * 1000) + ' / ' +
        Math.round(settings.turn_duration * 1000) + ' ms · settle ' +
        Math.round((settings.settle_duration ?? 0.6) * 1000) + ' ms' +
        (settings.invert_yaw ? ' · yaw inverted' : '') : '';
    const output = document.getElementById('steering-decision');
    if (!decision) {
        pathLine.removeAttribute('points');
        pathWaypoint.setAttribute('visibility', 'hidden');
        output.textContent = 'Waiting for a prediction.';
        return;
    }
    const scale = 90 / Math.max(0.25, ...decision.path.map(p => Math.max(Math.abs(p[0]), Math.abs(p[1]))));
    const points = decision.path.map(([forward, left]) => [100 - left * scale, 110 - forward * scale]);
    pathLine.setAttribute('points', [[100, 110], ...points].map(p => p.join(',')).join(' '));
    const [x, y] = points[decision.waypoint - 1];
    pathWaypoint.setAttribute('cx', x);
    pathWaypoint.setAttribute('cy', y);
    pathWaypoint.setAttribute('visibility', 'visible');
    const pulse = decision.duration === null ? 'no turn' :
        Math.round(decision.duration * 1000) + ' ms planned';
    output.textContent = (decision.maneuver === 'turn' ? 'Turn in place' : 'Forward') +
        ' · waypoint ' + decision.waypoint + ' · bearing ' +
        (decision.heading_rad * 180 / Math.PI).toFixed(1) + '° · yaw command ' +
        decision.requested_turn.toFixed(1) + ' → ' + decision.command[2].toFixed(1) +
        ' · ' + pulse + ' · frame age at decision ' + Math.round(decision.age_ms) + ' ms';
}
promptInput.addEventListener('input', updateButtons);
socket.on('vla_status', function(status) {
    available = socket.connected && status.state !== 'offline';
    ready = available && status.ready === true;
    document.getElementById('vla-state').textContent = status.state || 'Unknown';
    document.getElementById('vla-mode').textContent = status.move ? 'MOTION ENABLED' : 'Dry run';
    document.getElementById('vla-camera').textContent = status.camera_ok ? 'Camera receiving' : 'Waiting for camera';
    const values = Array.isArray(status.command) ? status.command : [0, 0, 0];
    document.getElementById('vla-command').textContent = ['vx', 'vy', 'turn'].map(function(name, i) {
        return name + ' ' + Number(values[i] || 0).toFixed(1);
    }).join(' · ');
    document.getElementById('vla-latency').textContent = Number.isFinite(status.latency_ms) ?
        (status.latency_ms / 1000).toFixed(2) + ' s inference · ' + status.predictions + ' predictions' : '';
    if (status.error) errorText.textContent = status.error;
    renderSteering(status.steering, status.decision);
    if (Number.isInteger(status.camera_pitch) && status.camera_pitch !== appliedPitch) {
        appliedPitch = status.camera_pitch;
        pitch.value = appliedPitch;
        pitch.oninput();
    }
    document.getElementById('pitch-status').textContent = Number.isInteger(status.camera_pitch) ?
        (status.move ? 'Requested ' : 'Dry run request ') + status.camera_pitch + '° · Prompt resumes navigation.' :
        'Set angle pauses navigation.';
    updateButtons();
});
socket.on('disconnect', function() {
    available = ready = false;
    applied = '';
    appliedPitch = null;
    renderSteering(null, null);
    document.getElementById('vla-state').textContent = 'Disconnected';
    updateButtons();
});
video.onerror = function() {
    setTimeout(function() { video.src = '/video/mjpeg?t=' + Date.now(); }, 2000);
};
