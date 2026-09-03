/**
 * Node self-test for RuTatSubtitles (invoked from pytest).
 *
 * Usage:
 *     node subtitles_selftest.js /path/to/web_client/js/subtitles.js
 */
require(process.argv[2]);
const S = globalThis.RuTatSubtitles;
const store = new S.SubtitleStore(3);
const a = store.apply({
  subtitle_id: "sub_1",
  speaker_id: "u_you",
  speaker_name: "Ты",
  text: "Әни",
  status: "partial",
  language: "mixed",
});
if (!a || a.isNew !== true || a.row.text !== "Әни") {
  process.exit(2);
}
const b = store.apply({
  subtitle_id: "sub_1",
  speaker_id: "u_you",
  speaker_name: "Ты",
  text: "Әни, сегодня дома",
  status: "partial",
});
if (b.isNew || b.row.text !== "Әни, сегодня дома" || store.items.length !== 1) {
  process.exit(3);
}
store.apply({
  subtitle_id: "sub_1",
  speaker_id: "u_you",
  speaker_name: "Ты",
  text: "Әни, сегодня дома.",
  status: "final",
});
const frozen = store.apply({
  subtitle_id: "sub_1",
  speaker_id: "u_you",
  speaker_name: "Ты",
  text: "ignored",
  status: "partial",
});
if (frozen.row.text !== "Әни, сегодня дома." || frozen.row.status !== "final") {
  process.exit(4);
}
store.apply({
  subtitle_id: "sub_2",
  speaker_id: "u_mama",
  speaker_name: "Mama",
  text: "Хорошо",
  status: "final",
});
store.apply({
  subtitle_id: "sub_3",
  speaker_id: "u_sister",
  speaker_name: "Сестра",
  text: "Ок",
  status: "final",
});
store.apply({
  subtitle_id: "sub_4",
  speaker_id: "u_you",
  speaker_name: "Ты",
  text: "drop oldest",
  status: "final",
});
if (store.items.length !== 3 || store.items[0].id !== "sub_2") {
  process.exit(5);
}
if (S.speakerColor("u_you") !== S.speakerColor("u_you")) {
  process.exit(6);
}
const mapped = S.fromAsrEvent("asr.partial", {
  subtitle_id: "sub_x",
  speaker_id: "u_you",
  speaker_name: "Ты",
  text: "hi",
  language: "ru",
});
if (!mapped || mapped.status !== "partial") {
  process.exit(7);
}
if (S.fromAsrEvent("asr.info", {}) !== null) {
  process.exit(8);
}
