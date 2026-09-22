/* Evidence-based MAVLink command/state reconstruction.
   Accepted takeoff means the command was accepted; it does not prove airborne state. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.StateAnalysis = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function analyze(frames) {
    const ordered = [...(frames || [])].sort((a, b) => a.offset - b.offset);
    const timeline = [], links = [], violations = [], pending = new Map();
    let state = 'unknown';

    function transition(frame, next, evidence) {
      if (next === state) return;
      timeline.push({ offset: frame.offset, from: state, to: next, evidence });
      state = next;
    }
    function enqueue(command, frame) {
      if (!pending.has(command)) pending.set(command, []);
      pending.get(command).push(frame);
    }

    for (const frame of ordered) {
      if (!frame.family.startsWith('MAVLink') || frame.crc === 'invalid' || !frame.fields) continue;
      const fields = frame.fields;
      if (frame.messageId === 0 && frame.componentId === 1) {
        transition(frame, fields.armed ? 'armed' : 'disarmed', `HEARTBEAT armed=${fields.armed}`);
      }
      if (frame.messageId === 76) {
        enqueue(fields.command, frame);
        if (fields.command === 400) transition(frame, fields.param1 >= 0.5 ? 'arming-requested' : 'disarming-requested', `COMMAND_LONG ${fields.commandName}`);
        if (fields.command === 22) {
          if (state !== 'armed') violations.push({ offset: frame.offset, type: 'precondition', detail: `TAKEOFF 出现时状态为 ${state}，未获得已解锁证据。` });
          transition(frame, 'takeoff-requested', `COMMAND_LONG ${fields.commandName}`);
        }
      }
      if (frame.messageId === 77) {
        const queue = pending.get(fields.command) || [];
        const request = queue.shift();
        if (request) {
          links.push({ command: fields.commandName, requestOffset: request.offset, ackOffset: frame.offset, result: fields.resultName });
          if (fields.result === 0 && fields.command === 400) transition(frame, 'armed', 'ARM_DISARM ACK accepted');
          else if (fields.result === 0 && fields.command === 22) transition(frame, 'takeoff-accepted', 'TAKEOFF ACK accepted');
          else if (fields.result !== 5) transition(frame, 'command-rejected', `${fields.commandName} ACK ${fields.resultName}`);
        } else {
          violations.push({ offset: frame.offset, type: 'orphan-ack', detail: `${fields.commandName} 应答之前未发现对应命令。` });
        }
      }
    }

    for (const queue of pending.values()) {
      for (const request of queue) violations.push({ offset: request.offset, type: 'missing-ack', detail: `${request.fields.commandName} 在当前捕获结束前没有对应应答。` });
    }
    return {
      schema: 'protocol-state-evidence-v1',
      finalState: state,
      timeline,
      links,
      violations,
      boundary: '状态只来自当前捕获中的有效报文；TAKEOFF 被接受不等于飞行器已经离地。',
    };
  }

  return { analyze };
});
