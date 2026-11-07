"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { computeDodgeTarget } = require("../src/main/dodge");

test("computeDodgeTarget does not move when cursor is far away", () => {
  const res = computeDodgeTarget({
    cursorX: 100,
    cursorY: 100,
    winX: 1200,
    winY: 300,
    winWidth: 420,
    winHeight: 640,
    workArea: { x: 0, y: 0, width: 1920, height: 1040 },
  });
  assert.equal(res.shouldMove, false);
  assert.equal(res.targetX, 1200);
});

test("computeDodgeTarget dodges away when cursor approaches avatar body", () => {
  const res = computeDodgeTarget({
    cursorX: 1180,
    cursorY: 650,
    winX: 1000,
    winY: 300,
    winWidth: 420,
    winHeight: 640,
    workArea: { x: 0, y: 0, width: 1920, height: 1040 },
  });
  assert.equal(res.shouldMove, true);
  assert.notEqual(res.targetX, 1000);
});

test("computeDodgeTarget escapes corner when pinned at screen edge", () => {
  const res = computeDodgeTarget({
    cursorX: 1700,
    cursorY: 750,
    winX: 1500, // At right edge (1500 + 420 = 1920)
    winY: 400,  // At bottom edge (400 + 640 = 1040)
    winWidth: 420,
    winHeight: 640,
    workArea: { x: 0, y: 0, width: 1920, height: 1040 },
  });
  assert.equal(res.shouldMove, true);
  assert.ok(res.targetX < 500, `Expected hop to left side, got ${res.targetX}`);
});

test("computeDodgeTarget pauses dodge when Alt key is held", () => {
  const res = computeDodgeTarget({
    cursorX: 1210,
    cursorY: 670,
    winX: 1000,
    winY: 300,
    winWidth: 420,
    winHeight: 640,
    workArea: { x: 0, y: 0, width: 1920, height: 1040 },
    altPressed: true,
  });
  assert.equal(res.shouldMove, false);
});
