"use strict";

/**
 * Pure, testable mouse-dodge calculator for the Makise Kurisu overlay window.
 * When the cursor enters the repulsion radius around the avatar center, computes
 * the smooth target position inside the monitor workArea, jumping to the opposite
 * side if cornered.
 */
function computeDodgeTarget({
  cursorX,
  cursorY,
  winX,
  winY,
  winWidth,
  winHeight,
  workArea,
  repelRadius = 155,
  pushStep = 140,
  altPressed = false,
}) {
  if (altPressed) {
    return { shouldMove: false, targetX: winX, targetY: winY };
  }

  // Avatar body anchor is roughly horizontally centered and 58% down the window
  const centerX = winX + winWidth * 0.5;
  const centerY = winY + winHeight * 0.58;
  const dx = centerX - cursorX;
  const dy = centerY - cursorY;
  const dist = Math.hypot(dx, dy);

  if (dist >= repelRadius) {
    return { shouldMove: false, targetX: winX, targetY: winY };
  }

  const minX = workArea.x;
  const minY = workArea.y;
  const maxX = workArea.x + workArea.width - winWidth;
  const maxY = workArea.y + workArea.height - winHeight;

  // Direction unit vector away from cursor
  const norm = dist > 1 ? dist : 1;
  const ux = dist > 1 ? dx / norm : 1;
  const uy = dist > 1 ? dy / norm : -0.5;

  let nextX = Math.round(winX + ux * pushStep);
  let nextY = Math.round(winY + uy * pushStep);

  nextX = Math.max(minX, Math.min(maxX, nextX));
  nextY = Math.max(minY, Math.min(maxY, nextY));

  // If clamped against a corner and barely moved (< 25px), hop to the opposite horizontal side
  if (Math.hypot(nextX - winX, nextY - winY) < 25) {
    const midScreenX = workArea.x + workArea.width * 0.5;
    nextX = centerX < midScreenX ? maxX - 24 : minX + 24;
    nextY = Math.max(minY, Math.min(maxY, winY));
  }

  return {
    shouldMove: nextX !== winX || nextY !== winY,
    targetX: nextX,
    targetY: nextY,
  };
}

module.exports = { computeDodgeTarget };
