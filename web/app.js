"use strict";
// Native browser UI. All user-facing prose is localized; no remote assets.
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const main = $("#main");
const state = {
  language: "es", dictionaries: {}, user: null, registrationOpen: true,
  dashboard: null, attempt: null, index: 0, busy: false, routeId: 0,
  skew: 0, heartbeatBusy: false, authMode: "login", historyBank: "", historyKind: "all", historyPage: 0,
  reviewFilter: "all", reviewDomain: "all", reviewId: null, importFile: null, importPreview: null,
  toastTimer: null, lastTimeoutCheck: 0, saveFailed: false, lastRoute: null,
};
const local = {
  get(key) { try { return localStorage.getItem(key); } catch (_) { return null; } },
  set(key, value) { try { localStorage.setItem(key, String(value)); } catch (_) { /* Progress is server-side. */ } },
};
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function t(key, values = {}) {
  let value = state.dictionaries[state.language]?.[key] ?? state.dictionaries.en?.[key] ?? key;
  for (const [name, replacement] of Object.entries(values)) value = value.replaceAll(`{${name}}`, String(replacement));
  return value;
}
const text = value => typeof value === "string" ? value : value?.[state.language] ?? value?.en ?? value?.es ?? "";
const number = value => new Intl.NumberFormat(state.language, {maximumFractionDigits: 1}).format(value);
const percent = value => value == null ? "—" : number(value) + "%";
const date = seconds => new Date(seconds * 1000).toLocaleString(state.language === "es" ? "es-CO" : "en-US", {dateStyle:"medium", timeStyle:"short"});
const timeText = seconds => {
  const n = Math.max(0, Math.ceil(seconds || 0));
  return `${String(Math.floor(n / 60)).padStart(2, "0")}:${String(n % 60).padStart(2, "0")}`;
};
const path = () => (location.hash || "#home").slice(1);
const isAttempt = () => state.attempt && path() === `attempt/${state.attempt.id}`;
function go(route) { if (path() === route) renderRoute(); else location.hash = route; }
function safeURL(value) { try { const url = new URL(value); return url.protocol === "https:" ? url.href : "#"; } catch (_) { return "#"; } }
function toast(message, error = false) {
  const el = $("#toast"); clearTimeout(state.toastTimer);
  el.textContent = message; el.className = "toast" + (error ? " error" : "");
  state.toastTimer = setTimeout(() => el.classList.add("hidden"), error ? 6500 : 4000);
}
function errorText(error) {
  let message = t(error.code || "network_error");
  if (error.data?.path) message += ` ${error.data.path}: ${t("rule_" + error.data.rule)}`;
  return message;
}
function connection(failed) {
  $("#connection").textContent = failed ? t("network_error") : "";
  $("#connection").classList.toggle("hidden", !failed);
}
async function request(endpoint, body, raw = false, file = false) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), raw ? 30000 : 15000);
  try {
    const headers = {};
    if (state.user && endpoint !== "/api/session") headers["X-Profile-ID"] = String(state.user.id);
    if (body !== undefined) { headers["X-Local-App"] = "1"; headers["Content-Type"] = raw ? "application/zip" : "application/json"; }
    const response = await fetch(endpoint, {method:body === undefined ? "GET" : "POST", credentials:"same-origin", cache:"no-store", headers,
      body:body === undefined ? undefined : raw ? body : JSON.stringify(body), signal:controller.signal});
    connection(false);
    if (!response.ok) {
      const data = await response.json(); const error = new Error(data.code); error.code = data.code; error.status = response.status; error.data = data; throw error;
    }
    return file ? response.blob() : response.json();
  } catch (error) {
    if (!error.status) { connection(true); error.code = "network_error"; }
    throw error;
  } finally { clearTimeout(timeout); }
}
async function download(endpoint, filename) {
  try {
    const blob = await request(endpoint, undefined, false, true);
    const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = filename;
    document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  } catch (error) { handleError(error); }
}
function handleError(error) {
  if (error.code === "profile_changed" || error.code === "sign_in_required") {
    state.user = null; state.attempt = null; state.dashboard = null; renderHeader(); renderAuth();
  }
  if (error.data?.attempt) { acceptAttempt(error.data.attempt); if (isAttempt()) renderAttempt(); }
  if (error.data?.active_id) go(`attempt/${error.data.active_id}`);
  toast(errorText(error), true);
}
function busy(button, active) { if (button) { button.disabled = active; button.setAttribute("aria-busy", String(active)); } }
function renderHeader() {
  document.documentElement.lang = state.language;
  document.title = "AWS Practice Local";
  const route = path().split("/")[0];
  $("#header").innerHTML = `<div class="topbar"><a href="#home" class="brand"><img src="/favicon.svg" alt=""><span>AWS Practice<small>LOCAL · v4.0</small></span></a>
    ${state.user ? `<nav class="nav" aria-label="${esc(t("home"))}">${["home","history","profile",...(state.user.role === "admin" ? ["admin"] : [])].map(name => `<a href="#${name}" class="${route === name ? "active" : ""}" ${route === name ? 'aria-current="page"' : ""}>${esc(t(name))}</a>`).join("")}</nav>` : ""}
    <div class="header-tools">${state.user ? `<span class="user-chip">${esc(state.user.display_name)}</span>` : ""}<label class="sr-only" for="language">${esc(t("language"))}</label>
      <select id="language"><option value="es" ${state.language === "es" ? "selected" : ""}>Español</option><option value="en" ${state.language === "en" ? "selected" : ""}>English</option></select>
      ${state.user ? `<button id="logout" class="ghost small">${esc(t("sign_out"))}</button>` : ""}</div></div>`;
  $("#skip-link").textContent = t("skip_main");
  $("#language").onchange = async event => {
    const language = event.target.value;
    if (state.busy) { event.target.value = state.language; return; }
    state.language = language; local.set("practice-language", language);
    if (state.user) {
      try { const result = await request("/api/profile", {display_name:state.user.display_name, language}); state.user = result.user; }
      catch (error) { handleError(error); }
    }
    renderRoute();
  };
  if ($("#logout")) $("#logout").onclick = async () => {
    if (state.busy) return;
    try { await request("/api/logout", {}); state.user = null; state.attempt = null; state.dashboard = null; state.authMode = "login"; go("home"); }
    catch (error) { handleError(error); }
  };
  $("#footer").innerHTML = `<div class="footer-row"><div><strong>AWS Practice Local 4.0</strong><br>${esc(t("original_notice"))}</div>
    ${state.user ? `<button id="footer-kit" class="ghost small">${esc(t("schema_kit"))}</button>` : ""}</div>`;
  if ($("#footer-kit")) $("#footer-kit").onclick = () => download("/api/schema.zip", "question-bank-authoring-kit.zip");
}
function renderAuth() {
  const register = state.authMode === "register" && state.registrationOpen;
  main.innerHTML = `<div class="auth-layout"><section class="auth-intro"><p class="eyebrow">${esc(t("local_badge"))}</p><h1>${esc(t("welcome"))}</h1><p class="muted">${esc(t("welcome_body"))}</p>
    <div class="auth-mark"><span>01</span><p class="muted">${esc(t("local_note"))}</p></div></section>
    <section class="card auth-card"><h2>${esc(t(register ? "create_profile" : "sign_in"))}</h2>
    <form id="auth-form" class="form-grid"><div><label for="username">${esc(t("username"))}</label><input id="username" name="username" autocomplete="username" minlength="3" maxlength="32" required>${register ? `<p class="hint">${esc(t("username_help"))}</p>` : ""}</div>
    ${register ? `<div><label for="display-name">${esc(t("display_name"))}</label><input id="display-name" name="display_name" autocomplete="nickname" maxlength="64" required></div>` : ""}
    <div><label for="password">${esc(t("password"))}</label><input id="password" name="password" type="password" autocomplete="${register ? "new-password" : "current-password"}" minlength="${register ? 8 : 1}" maxlength="128" required>${register ? `<p class="hint">${esc(t("password_help"))}</p>` : ""}</div>
    ${register ? `<div><label for="confirm-password">${esc(t("confirm_password"))}</label><input id="confirm-password" type="password" autocomplete="new-password" minlength="8" maxlength="128" required></div>` : ""}
    <div id="auth-error" class="hidden callout error-box" role="alert"></div><button class="primary full" type="submit">${esc(t(register ? "create_profile" : "sign_in"))}</button></form>
    ${state.registrationOpen ? `<div class="auth-switch">${esc(t(register ? "have_profile" : "new_here"))} <button class="ghost small" id="auth-toggle">${esc(t(register ? "sign_in" : "create_profile"))}</button></div>` : `<p class="hint spaced">${esc(t("registration_closed"))}</p>`}
    ${location.protocol !== "https:" ? `<p class="hint spaced">${esc(t("http_warning"))}</p>` : ""}</section></div>`;
  if ($("#auth-toggle")) $("#auth-toggle").onclick = () => { state.authMode = register ? "login" : "register"; renderAuth(); };
  $("#auth-form").onsubmit = async event => {
    event.preventDefault(); const form = event.currentTarget, button = $("button[type=submit]", form); busy(button, true);
    const errorBox = $("#auth-error"); errorBox.classList.add("hidden");
    try {
      if (register && $("#password").value !== $("#confirm-password").value) throw {code:"password_mismatch"};
      const body = {username:$("#username").value, password:$("#password").value, language:state.language};
      if (register) body.display_name = $("#display-name").value;
      const result = await request(register ? "/api/register" : "/api/login", body);
      state.user = result.user; state.language = result.user.language; state.dashboard = null;
      local.set("practice-language", state.language); go("home");
    } catch (error) { errorBox.textContent = errorText(error); errorBox.classList.remove("hidden"); }
    finally { busy(button, false); }
  };
}
function fallback(languages) {
  return languages.includes(state.language) ? "" : `<div class="callout warning spaced">${esc(t("bank_language_fallback", {language:t(languages[0])}))}</div>`;
}
async function renderHome(routeId) {
  const data = await request("/api/dashboard"); if (routeId !== state.routeId) return; state.dashboard = data;
  main.innerHTML = `<div class="page-heading"><p class="eyebrow">${esc(t("hello", {name:state.user.display_name}))}</p><h1>${esc(t("practice_title"))}</h1><p class="muted">${esc(t("practice_subtitle"))}</p></div>
    ${state.user.default_password ? `<div class="callout warning spaced">${esc(t("admin_default_warning"))} <a href="#profile">${esc(t("change_password"))}</a></div>` : ""}
    ${data.active ? `<section class="card active-banner row between spaced"><div><p class="eyebrow">${esc(t("active_session"))}</p><h2>${esc(text(data.active.metadata.bank_title))}</h2><p class="muted">${esc(t(data.active.kind))} · ${esc(t("one_active"))}</p></div><a class="button accent" href="#attempt/${data.active.id}">${esc(t("resume"))}</a></section>` : ""}
    <div class="bank-grid spaced">${data.banks.map(bank => `<section class="card bank-card"><div class="bank-heading"><div class="row between"><span class="badge">${esc(bank.manifest.exam_code)}</span><span class="muted hint">${esc(t("version"))} ${esc(bank.version)} · ${bank.manifest.languages.map(language => language.toUpperCase()).join(" / ")}</span></div><h2 class="spaced">${esc(text(bank.manifest.title))}</h2><p class="muted hint">${number(bank.question_count)} ${esc(t("questions"))}</p></div>
      <div class="metrics"><div><div class="metric-value highlight">${percent(bank.stats.average)}</div><div class="metric-label">${esc(t("average"))}</div></div><div><div class="metric-value">${number(bank.stats.completed)}</div><div class="metric-label">${esc(t("completed"))}</div></div><div><div class="metric-value">${number(bank.stats.remaining)}</div><div class="metric-label">${esc(t("remaining"))} · ${esc(t("cycle", {cycle:bank.stats.cycle}))}</div></div></div>
      <p class="hint">${esc(bank.stats.average == null ? t("no_average") : t("average_detail", {count:bank.stats.recent_count}))}</p>
      <div class="mode-grid">${["quiz","exam","rush"].map(kind => { const mode = bank.settings[kind]; return `<div class="mode ${kind === "rush" ? "rush-mode" : ""}"><h3>${esc(t(kind))}</h3><p class="muted">${kind === "rush" ? esc(t("rush_card", {goal:mode.question_count, time:timeText(mode.duration_seconds)})) : `${mode.question_count} ${esc(t("questions"))}<br>${timeText(mode.duration_seconds)} · ${mode.question_count - mode.unscored_count} ${esc(t("scored").toLowerCase())}`}</p>${kind === "rush" ? `<p class="hint">${esc(t("rush_rules_short"))}</p>` : ""}<button class="${kind === "quiz" ? "primary" : ""} start" data-bank="${esc(bank.id)}" data-kind="${kind}" ${data.active ? "disabled" : ""}>${esc(t("start_" + kind))}</button></div>`; }).join("")}</div>${fallback(bank.manifest.languages)}</section>`).join("")}</div>
      ${data.banks.length ? "" : `<div class="card empty"><h2>${esc(t("no_banks"))}</h2><p class="muted">${esc(t("no_banks_help"))}</p>${state.user.role === "admin" ? `<a class="button primary" href="#admin">${esc(t("import_bank"))}</a>` : ""}</div>`}
      <p class="hint spaced">${esc(t("score_notice"))}</p>`;
  $$(".start").forEach(button => button.onclick = async () => {
    if (state.busy) return; state.busy = true; $$(".start").forEach(b => busy(b, true));
    try { const attempt = await request("/api/attempts", {bank_id:button.dataset.bank, kind:button.dataset.kind}); acceptAttempt(attempt); go(`attempt/${attempt.id}`); }
    catch (error) { handleError(error); }
    finally { state.busy = false; $$(".start").forEach(b => busy(b, false)); }
  });
}
function acceptAttempt(attempt) {
  const changed = !state.attempt || state.attempt.id !== attempt.id;
  state.attempt = attempt; state.skew = attempt.server_now * 1000 - Date.now();
  if (changed) {
    state.saveFailed = false;
    state.index = Math.min(attempt.total - 1, Math.max(0, Number(local.get("question-index-" + attempt.id)) || 0));
  }
  if (attempt.kind === "rush" && attempt.status === "active") state.index = attempt.rush.index;
  if (state.reviewId !== attempt.id) { state.reviewId = attempt.id; state.reviewFilter = "all"; state.reviewDomain = "all"; }
}
function setIndex(index) {
  state.index = Math.max(0, Math.min(state.attempt.total - 1, index));
  local.set("question-index-" + state.attempt.id, state.index); renderAttempt(); window.scrollTo(0, 0);
  $(".question-prompt")?.focus({preventScroll:true});
}
function renderAttempt() {
  const attempt = state.attempt; if (!attempt || !isAttempt()) return;
  if (attempt.status !== "active") return renderReport();
  if (attempt.kind === "rush") return renderRush();
  const q = attempt.questions[state.index];
  main.innerHTML = `<section class="session-top"><div class="session-title"><h1>${esc(text(attempt.metadata.bank_title))}</h1><div class="muted">${esc(t(attempt.kind))} · ${esc(t("answered_count", {answered:attempt.answered,total:attempt.total}))}</div></div><div class="timer" id="timer"><small>${esc(t("time_remaining"))}</small><strong id="clock">${timeText(attempt.deadline - (Date.now() + state.skew) / 1000)}</strong></div></section>
    ${fallback(attempt.metadata.languages)}
    <div class="session-layout"><section class="card question-card"><div class="row between"><span class="eyebrow">${esc(t("question_number", {number:state.index + 1,total:attempt.total}))}</span><span class="save-state" id="save-state" role="status">${esc(t(state.saveFailed ? "save_failed" : "saved"))}</span></div>
    <div class="question-prompt" tabindex="-1">${esc(text(q.prompt))}</div><span class="badge ${q.select_count > 1 ? "gold" : ""}">${esc(q.select_count === 1 ? t("select_one") : q.select_count === 2 ? t("select_two") : t("select_answers", {count:q.select_count}))}</span>
    <div class="choice-list" role="group" aria-label="${esc(t("question_number",{number:state.index+1,total:attempt.total}))}">${q.options.map((option, i) => `<label class="choice"><input type="${q.select_count === 1 ? "radio" : "checkbox"}" name="answer" value="${option.id}" ${q.selected.includes(option.id) ? "checked" : ""}><span class="choice-body"><span class="choice-letter">${String.fromCharCode(65+i)}.</span><span>${esc(text(option.text))}</span></span></label>`).join("")}</div>
    <div class="row between"><span class="selection-hint">${esc(t("selected_count", {selected:q.selected.length,required:q.select_count}))}</span><button id="clear-answer" class="ghost small">${esc(t("clear_answer"))}</button></div>
    <div class="question-actions"><div class="row between"><button id="flag-question" class="small ${q.flagged ? "accent" : ""}">${q.flagged ? "★ " : "☆ "}${esc(t(q.flagged ? "unflag" : "flag"))}</button><div class="actions"><button id="previous-question" ${state.index === 0 ? "disabled" : ""}>${esc(t("previous"))}</button><button id="next-question" class="primary">${esc(t(state.index === attempt.total-1 ? "submit" : "next"))}</button></div></div></div></section>
    <aside class="card nav-panel"><details ${window.innerWidth > 640 ? "open" : ""}><summary>${esc(t("question_map"))}</summary><div class="map">${attempt.questions.map((question,i) => `<button data-index="${i}" aria-label="${esc(t("question_number",{number:i+1,total:attempt.total}))}${question.flagged ? ' · '+esc(t("flag")) : ''}" ${i === state.index ? 'aria-current="step"' : ""} class="${question.selected.length === question.select_count ? "answered" : ""} ${i === state.index ? "current" : ""} ${question.flagged ? "flagged" : ""}">${i+1}</button>`).join("")}</div><p class="hint">${esc(t("map_legend"))}</p></details><button id="submit-session" class="primary full spaced">${esc(t("submit"))}</button><a href="#home" class="button ghost full small spaced">${esc(t("back_practice"))}</a></aside></div>`;
  $$("input[name=answer]").forEach(input => input.onchange = () => {
    if (state.busy) { renderAttempt(); return; }
    let selected = $$("input[name=answer]:checked").map(el => el.value);
    if (selected.length > q.select_count) { input.checked = false; toast(t("select_answers", {count:q.select_count}), true); return; }
    updateAnswer({selected});
  });
  $("#clear-answer").onclick = () => updateAnswer({selected:[]});
  $("#flag-question").onclick = () => updateAnswer({flagged:!q.flagged});
  $("#previous-question").onclick = () => { if (!state.busy) setIndex(state.index - 1); };
  $("#next-question").onclick = () => { if (!state.busy) state.index === attempt.total-1 ? submitDialog() : setIndex(state.index + 1); };
  $("#submit-session").onclick = submitDialog;
  $$(".map button").forEach(button => button.onclick = () => { if (!state.busy) setIndex(Number(button.dataset.index)); });
  tick();
}
function renderRush() {
  const attempt = state.attempt, rush = attempt.rush, feedback = rush.phase === "feedback";
  const q = feedback ? attempt.feedback : attempt.questions[0];
  main.innerHTML = `<section class="session-top"><div class="session-title"><h1>${esc(text(attempt.metadata.bank_title))}</h1><div class="muted">${esc(t("rush"))} · ${esc(t("rush_round", {round:rush.round_number}))}</div></div><div class="timer" id="timer"><small>${esc(t("time_remaining"))}</small><strong id="clock">${timeText(attempt.deadline - (Date.now()+state.skew)/1000)}</strong></div></section>
    ${fallback(attempt.metadata.languages)}
    <section class="card rush-stats" aria-label="${esc(t("rush_progress"))}"><div><span class="metric-label">${esc(t("rush_streak"))}</span><strong>${rush.streak}/${rush.goal}</strong><progress value="${rush.streak}" max="${rush.goal}" aria-label="${esc(t("rush_streak"))}"></progress></div><div><span class="metric-label">${esc(t("score"))}</span><strong>${percent(rush.percentage)}</strong><span class="hint">${esc(t("rush_fraction", {correct:rush.correct_count,generated:rush.generated_count}))}</span></div><div><span class="metric-label">${esc(t("rush_best_streak"))}</span><strong>${rush.best_streak}</strong><span class="hint">${esc(t("rush_failures", {count:rush.failures}))}</span></div></section>
    <div class="rush-layout spaced">${feedback ? `<section class="card rush-feedback"><div class="callout error-box" role="alert"><strong>${esc(t("rush_failed_title"))}</strong><p>${esc(t("rush_failed_body", {goal:rush.goal,round:rush.round_number}))}</p></div><div class="question-prompt" tabindex="-1">${esc(text(q.prompt))}</div><div class="rush-correction"><h2>${esc(t("rush_correct_answer"))}</h2>${q.options.filter(option=>option.correct).map(option=>`<p><strong>${String.fromCharCode(65+q.options.indexOf(option))}.</strong> ${esc(text(option.text))}</p>`).join("")}<h3>${esc(t("explanation"))}</h3><p>${esc(text(q.explanation))}</p></div><details class="rush-option-detail spaced"><summary>${esc(t("rush_option_analysis"))}</summary>${reviewContent(q)}</details><div class="rush-continue spaced"><p class="hint">${esc(t("rush_clock_running"))}</p><button id="rush-continue" class="primary full">${esc(t("rush_continue"))}</button></div></section>` : `<section class="card question-card"><div class="row between"><span class="eyebrow">${esc(t("question_number", {number:rush.streak+1,total:rush.goal}))}</span><span class="save-state" id="save-state" role="status">${esc(t(state.saveFailed ? "save_failed" : "saved"))}</span></div>
    <div class="question-prompt" tabindex="-1">${esc(text(q.prompt))}</div><span class="badge ${q.select_count>1?"gold":""}">${esc(q.select_count===1?t("select_one"):q.select_count===2?t("select_two"):t("select_answers",{count:q.select_count}))}</span>
    <div class="choice-list" role="group" aria-label="${esc(t("rush_answer"))}">${q.options.map((option,i)=>`<label class="choice"><input type="${q.select_count===1?"radio":"checkbox"}" name="answer" value="${option.id}" ${q.selected.includes(option.id)?"checked":""}><span class="choice-body"><span class="choice-letter">${String.fromCharCode(65+i)}.</span><span>${esc(text(option.text))}</span></span></label>`).join("")}</div>
    <div class="row between"><span class="selection-hint">${esc(t("selected_count",{selected:q.selected.length,required:q.select_count}))}</span><button id="clear-answer" class="ghost small">${esc(t("clear_answer"))}</button></div><p class="hint spaced">${esc(t("rush_confirmation_hint"))}</p><button id="rush-answer" class="primary full" ${q.selected.length!==q.select_count || state.saveFailed?"disabled":""}>${esc(t("rush_answer"))}</button></section>`}
    <aside class="card rush-help"><h2>${esc(t("rush_how_to"))}</h2><p>${esc(t("rush_rules", {goal:rush.goal}))}</p><p class="hint">${esc(t("rush_score_notice"))}</p><p class="hint">${esc(t("rush_cycle_notice"))}</p><button id="submit-session" class="full">${esc(t("rush_end"))}</button><a href="#home" class="button ghost full small spaced">${esc(t("back_practice"))}</a></aside></div>`;
  if (feedback) $("#rush-continue").onclick = () => sendRush("continue");
  else {
    $$("input[name=answer]").forEach(input=>input.onchange=()=>{
      if(state.busy){renderAttempt();return;}
      const selected=$$("input[name=answer]:checked").map(el=>el.value);
      if(selected.length>q.select_count){input.checked=false;toast(t("select_answers",{count:q.select_count}),true);return;}
      updateAnswer({selected});
    });
    $("#clear-answer").onclick=()=>updateAnswer({selected:[]});
    $("#rush-answer").onclick=()=>sendRush("answer");
  }
  $("#submit-session").onclick=submitDialog;
  tick();
}
async function sendRush(action) {
  if(state.busy || state.attempt?.status!=="active")return;
  state.busy=true; const attempt=state.attempt, q=attempt.questions[0];
  $$(".rush-layout button,.rush-layout input").forEach(el=>el.disabled=true);
  try {
    const body={revision:attempt.revision};
    if(action==="answer"){body.index=attempt.rush.index;body.selected=q.selected;}
    const result=await request(`/api/attempts/${attempt.id}/rush-${action}`,body);
    state.saveFailed=false;acceptAttempt(result);window.scrollTo(0,0);
    if(action==="answer" && result.rush.correct_count>attempt.rush.correct_count) $("#announcer").textContent=t("rush_correct_progress",{streak:result.rush.streak,goal:result.rush.goal});
  } catch(error){handleError(error);}
  finally{state.busy=false;renderAttempt();$(".question-prompt")?.focus({preventScroll:true});}
}
async function updateAnswer(change) {
  if (state.busy || !state.attempt || state.attempt.status !== "active") return;
  state.busy = true;
  if ($("#save-state")) $("#save-state").textContent = t("saving");
  $$(".question-card button,.question-card input,.map button,#submit-session").forEach(el => el.disabled = true);
  try { const result = await request(`/api/attempts/${state.attempt.id}/answer`, {revision:state.attempt.revision,index:state.index,...change}); state.saveFailed = false; acceptAttempt(result); }
  catch (error) { state.saveFailed = true; handleError(error); }
  finally { state.busy = false; renderAttempt(); }
}
function confirmDialog(title, body, callback) {
  const dialog = $("#confirm-dialog");
  dialog.innerHTML = `<h2>${esc(title)}</h2><p>${esc(body)}</p><div class="actions"><button id="dialog-cancel">${esc(t("keep_reviewing"))}</button><button id="dialog-confirm" class="primary">${esc(t("submit"))}</button></div>`;
  $("#dialog-cancel").onclick = () => dialog.close();
  $("#dialog-confirm").onclick = () => { dialog.close(); callback(); };
  dialog.showModal();
}
function submitDialog() {
  if (state.busy || state.attempt?.status !== "active") return;
  const attempt = state.attempt;
  confirmDialog(t(attempt.kind === "rush" ? "rush_end_title" : "submit_title"), attempt.kind === "rush" ? t("rush_end_body") : t("submit_body", {answered:attempt.answered,total:attempt.total}), async () => {
    state.busy = true;
    try { acceptAttempt(await request(`/api/attempts/${attempt.id}/finish`, {revision:attempt.revision})); renderAttempt(); }
    catch (error) { handleError(error); }
    finally { state.busy = false; }
  });
}
function tick() {
  if (!isAttempt() || state.attempt.status !== "active" || !$("#clock")) return;
  const remaining = state.attempt.deadline - (Date.now() + state.skew)/1000;
  $("#clock").textContent = timeText(remaining); $("#timer").classList.toggle("urgent", remaining <= 120);
  if (remaining <= 0 && Date.now() - state.lastTimeoutCheck > 1200) { state.lastTimeoutCheck = Date.now(); heartbeat(); }
}
async function heartbeat() {
  if (!isAttempt() || state.attempt.status !== "active" || state.busy || state.heartbeatBusy) return;
  state.heartbeatBusy = true; const id = state.attempt.id, revision = state.attempt.revision;
  try {
    const result = await request(`/api/attempts/${id}`);
    if (isAttempt() && state.attempt.id === id && !state.busy && result.revision >= state.attempt.revision) {
      acceptAttempt(result);
      if (result.revision !== revision || result.status !== "active") renderAttempt();
    }
  } catch (error) { if (error.code !== "network_error") handleError(error); }
  finally { state.heartbeatBusy = false; }
}
function renderReport() {
  const attempt = state.attempt, result = attempt.result;
  main.innerHTML = `<div class="page-heading"><p class="eyebrow">${esc(t("report"))} · ${esc(attempt.metadata.exam_code)}</p><h1>${esc(t(attempt.kind))}</h1><p class="muted">${esc(date(attempt.finished_at))} · ${esc(t("version"))} ${esc(attempt.bank_version)}</p><div class="actions no-print"><a class="button primary" href="#home">${esc(t("back_practice"))}</a><button id="download-result">${esc(t("download_result"))}</button><button id="print-report">${esc(t("print"))}</button></div></div>
    ${fallback(attempt.metadata.languages)}<div class="report-metrics"><section class="card score-card"><div class="metric-label muted">${esc(t("score"))}</div><div class="metric-value">${percent(result.percentage)}</div><p class="muted">${esc(t("correct_count",{correct:result.correct,total:result.scored_total}))}</p></section><section class="card"><div class="metric-label">${esc(t("elapsed"))}</div><div class="metric-value">${timeText(result.elapsed_seconds)}</div><p class="hint">${esc(t(result.reason))}</p><p class="hint">${result.unanswered} ${esc(t("unanswered").toLowerCase())} · ${result.incomplete} ${esc(t("incomplete").toLowerCase())}</p></section>${attempt.kind === "rush" ? `<section class="card"><div class="metric-label">${esc(t("rush_best_streak"))}</div><div class="metric-value">${result.rush.best_streak}/${result.rush.goal}</div><span class="badge ${result.rush.completed ? "good" : "gold"}">${esc(t(result.rush.completed ? "rush_completed" : "rush_not_completed"))}</span><p class="hint">${esc(t("rush_report_detail", {rounds:result.rush.rounds,failures:result.rush.failures,confirmed:result.rush.confirmed}))}</p></section>` : `<section class="card"><div class="metric-label">${esc(t("practice_target"))}</div><div class="metric-value">${percent(result.target_percentage)}</div><span class="badge ${result.target_met ? "good" : "gold"}">${esc(t(result.target_met ? "target_met" : "target_not_met"))}</span><p class="hint">${esc(t("all_correct",{correct:result.all_correct,total:result.total}))}</p></section>`}</div>
    <div class="callout">${esc(t(attempt.kind === "rush" ? "rush_score_notice" : "score_notice"))}</div><section class="card spaced"><h2>${esc(t("domain_report"))}</h2><div class="domain-grid">${Object.entries(result.domains).map(([id,domain]) => `<div class="domain-card"><p><strong>${esc(text(domain.name))}</strong></p><div class="row between"><span>${domain.correct}/${domain.total} ${esc(t("scored").toLowerCase())}</span><strong>${domain.total ? percent(100*domain.correct/domain.total) : "—"}</strong></div><progress value="${domain.correct}" max="${Math.max(1,domain.total)}" aria-label="${esc(text(domain.name))}"></progress></div>`).join("")}</div>${result.distribution_adjusted ? `<p class="hint">${esc(t("distribution_note"))}</p>` : ""}</section>
    <section class="spaced"><div class="row between"><h2>${esc(t("answer_review"))}</h2><div class="actions no-print"><button id="expand-all" class="small">${esc(t("expand_all"))}</button><button id="collapse-all" class="small">${esc(t("collapse_all"))}</button></div></div>
    <div class="filters no-print"><div><label for="review-filter">${esc(t("report"))}</label><select id="review-filter">${["all","incorrect","unanswered",...(attempt.kind === "rush" ? ["skipped","unconfirmed"] : [])].map(value => `<option value="${value}" ${state.reviewFilter === value ? "selected" : ""}>${esc(t(value === "incorrect" ? "incorrect_filter" : value))}</option>`).join("")}</select></div><div><label for="review-domain">${esc(t("domain_report"))}</label><select id="review-domain"><option value="all">${esc(t("all_domains"))}</option>${Object.entries(result.domains).map(([id,d]) => `<option value="${esc(id)}" ${state.reviewDomain === id ? "selected" : ""}>${esc(text(d.name))}</option>`).join("")}</select></div></div><div id="review-list" class="review-list"></div></section>`;
  $("#review-filter").onchange = event => { state.reviewFilter = event.target.value; renderReviewList(); };
  $("#review-domain").onchange = event => { state.reviewDomain = event.target.value; renderReviewList(); };
  $("#download-result").onclick = () => download(`/api/attempts/${attempt.id}/export`, `result-${attempt.id}.json`);
  $("#expand-all").onclick = () => $$(".review-question").forEach(el => el.open = true);
  $("#collapse-all").onclick = () => $$(".review-question").forEach(el => el.open = false);
  $("#print-report").onclick = () => {
    state.reviewFilter = "all"; state.reviewDomain = "all"; $("#review-filter").value = "all"; $("#review-domain").value = "all";
    renderReviewList(); $$(".review-question").forEach(el => el.open = true); window.print();
  };
  renderReviewList();
}
function reviewContent(q) {
  return `<p class="hint">${esc(text(q.domain_name))} · ${esc(q.id)}</p>${q.options.map((option,i) => `<div class="review-option ${option.correct ? "is-correct" : q.selected.includes(option.id) ? "is-wrong" : ""}"><div class="row"><strong>${String.fromCharCode(65+i)}.</strong><span>${esc(text(option.text))}</span>${option.correct ? `<span class="badge good">${esc(t("correct_choice"))}</span>` : ""}${q.selected.includes(option.id) ? `<span class="badge ${option.correct ? "good" : "bad"}">${esc(t("your_choice"))}</span>` : ""}</div><p>${esc(text(option.explanation))}</p></div>`).join("")}
    <div class="explanation"><strong>${esc(t("explanation"))}</strong><p>${esc(text(q.explanation))}</p></div>${q.notes ? `<div class="callout warning spaced"><strong>${esc(t("content_note"))}</strong><p>${esc(text(q.notes))}</p></div>` : ""}${q.references.length ? `<div class="sources"><strong>${esc(t("references"))}</strong>${q.references.map(ref => `<a href="${esc(safeURL(ref.url))}" target="_blank" rel="noopener noreferrer">${esc(text(ref.title))} ↗</a>`).join("")}</div>` : ""}`;
}
function renderReviewList() {
  const questions = state.attempt.questions.map((question,index) => ({question,index})).filter(({question:q}) =>
    (state.reviewDomain === "all" || q.domain_id === state.reviewDomain) &&
    (state.reviewFilter === "all" || (state.reviewFilter === "incorrect" ? (state.attempt.kind === "rush" ? q.outcome === "incorrect" : !q.is_correct) : q.outcome === state.reviewFilter)));
  $("#review-list").innerHTML = questions.map(({question:q,index}) => `<details class="review-question"><summary><div class="review-summary"><div class="row"><strong>${esc(t("question_number",{number:index+1,total:state.attempt.total}))}</strong><span class="badge ${q.is_correct ? "good" : "bad"}">${esc(t(q.outcome))}</span>${q.round_number ? `<span class="badge">${esc(t("rush_round_item", {round:q.round_number,position:q.round_position}))}</span>` : ""}${!q.scored ? `<span class="badge gold">${esc(t("unscored"))}</span>` : ""}${q.incomplete ? `<span class="badge gold">${esc(t("incomplete"))}</span>` : ""}</div><p>${esc(text(q.prompt))}</p></div></summary>
    <div class="review-content">${reviewContent(q)}</div></details>`).join("") || `<div class="card empty">${esc(t("no_matches"))}</div>`;
}
async function renderHistory(routeId) {
  const [history, catalog] = await Promise.all([
    request(`/api/history?bank_id=${encodeURIComponent(state.historyBank)}&kind=${state.historyKind}&offset=${state.historyPage*25}`), request("/api/banks")]);
  if (routeId !== state.routeId) return;
  const bankNames = new Map(catalog.banks.map(bank => [bank.id, bank.manifest.title]));
  for (const bank of history.banks || []) if (!bankNames.has(bank.id)) bankNames.set(bank.id, bank.title);
  for (const attempt of history.items) if (!bankNames.has(attempt.bank_id)) bankNames.set(attempt.bank_id, attempt.metadata.bank_title);
  main.innerHTML = `<div class="page-heading"><p class="eyebrow">${esc(t("history"))}</p><h1>${esc(t("history_title"))}</h1><p class="muted">${esc(t("history_subtitle"))}</p></div>
    <div class="filters"><div><label for="history-bank">${esc(t("all_banks"))}</label><select id="history-bank"><option value="">${esc(t("all_banks"))}</option>${[...bankNames.entries()].map(([id,title]) => `<option value="${esc(id)}" ${state.historyBank === id ? "selected" : ""}>${esc(text(title))}</option>`).join("")}</select></div><div><label for="history-kind">${esc(t("all_modes"))}</label><select id="history-kind">${["all","quiz","exam","rush"].map(kind => `<option value="${kind}" ${state.historyKind === kind ? "selected" : ""}>${esc(t(kind === "all" ? "all_modes" : kind))}</option>`).join("")}</select></div></div>
    <div class="row between"><p class="muted">${esc(t("history_count",{count:history.total}))}</p><span class="hint">${esc(t("page",{page:state.historyPage+1}))}</span></div><div class="history-list">${history.items.map(attempt => `<article class="card history-row"><div><div class="row"><span class="badge">${esc(attempt.metadata.exam_code)}</span><h3>${esc(t(attempt.kind))}</h3></div><div class="muted">${esc(date(attempt.finished_at))} · ${timeText(attempt.result.elapsed_seconds)} · v${esc(attempt.bank_version)}</div></div><div class="history-score">${percent(attempt.result.percentage)}<div class="muted">${attempt.result.correct}/${attempt.result.scored_total}</div>${attempt.kind === "rush" ? `<div class="hint">${esc(t(attempt.result.rush.completed ? "rush_completed" : "rush_not_completed"))}</div>` : ""}</div><a href="#attempt/${attempt.id}" class="button">${esc(t("view_report"))}</a></article>`).join("") || `<div class="card empty">${esc(t("no_history"))}</div>`}</div>
    <div class="actions spaced"><button id="history-previous" ${state.historyPage===0 ? "disabled" : ""}>${esc(t("previous"))}</button><button id="history-next" ${((state.historyPage+1)*25 >= history.total) ? "disabled" : ""}>${esc(t("next"))}</button></div>`;
  $("#history-bank").onchange = event => { state.historyBank = event.target.value; state.historyPage = 0; renderRoute(); };
  $("#history-kind").onchange = event => { state.historyKind = event.target.value; state.historyPage = 0; renderRoute(); };
  $("#history-previous").onclick = () => { state.historyPage--; renderRoute(); };
  $("#history-next").onclick = () => { state.historyPage++; renderRoute(); };
}
function renderProfile() {
  main.innerHTML = `<div class="page-heading"><p class="eyebrow">${esc(state.user.username)} · ${esc(state.user.role === "admin" ? t("admin") : t("profile"))}</p><h1>${esc(t("profile_title"))}</h1><p class="muted">${esc(t("profile_subtitle"))}</p></div>${state.user.default_password ? `<div class="callout warning">${esc(t("admin_default_warning"))}</div>` : ""}
    <div class="profile-grid spaced"><section class="card"><h2>${esc(t("profile"))}</h2><form id="profile-form" class="form-grid"><div><label for="profile-name">${esc(t("display_name"))}</label><input id="profile-name" required maxlength="64" autocomplete="nickname" value="${esc(state.user.display_name)}"></div><button class="primary" type="submit">${esc(t("save"))}</button></form><div class="spaced"><h3>${esc(t("export_profile"))}</h3><p class="hint">${esc(t("export_note"))}</p><button id="export-profile">${esc(t("export_profile"))}</button></div></section>
    <section class="card"><h2>${esc(t("change_password"))}</h2><form id="password-form" class="form-grid">${[["current-password","current_password","current-password"],["new-password","new_password","new-password"],["repeat-password","confirm_password","new-password"]].map(([id,key,autocomplete]) => `<div><label for="${id}">${esc(t(key))}</label><input id="${id}" type="password" required minlength="${id==='current-password'?1:8}" maxlength="128" autocomplete="${autocomplete}"></div>`).join("")}<p class="hint">${esc(t("password_help"))}</p><button class="primary" type="submit">${esc(t("change_password"))}</button></form></section></div>`;
  $("#profile-form").onsubmit = async event => { event.preventDefault(); const button = $("button",event.currentTarget); busy(button,true);
    try { state.user = (await request("/api/profile",{display_name:$("#profile-name").value,language:state.language})).user; renderHeader(); toast(t("profile_saved")); } catch(error){handleError(error);} finally{busy(button,false);} };
  $("#password-form").onsubmit = async event => { event.preventDefault(); const button = $("button",event.currentTarget); busy(button,true);
    try { if ($("#new-password").value !== $("#repeat-password").value) throw {code:"password_mismatch"};
      await request("/api/password",{current_password:$("#current-password").value,new_password:$("#new-password").value}); state.user.default_password=false; renderProfile(); toast(t("password_changed"));
    } catch(error){handleError(error);} finally{busy(button,false);} };
  $("#export-profile").onclick = () => download("/api/export-profile",`profile-${state.user.username}.json`);
}
function formatFields(bank, kind) {
  const mode = bank.settings[kind];
  return `<section class="format-section ${kind === "rush" ? "rush-format" : ""}"><h3>${esc(t(kind))}</h3>${kind === "rush" ? `<p class="hint">${esc(t("rush_admin_help"))}</p>` : ""}<div class="format-fields">${(kind === "rush" ? ["question_count","duration_seconds"] : ["question_count","duration_seconds","unscored_count","target_percentage"]).map(field => `<div><label for="${bank.id}-${kind}-${field}">${esc(t(kind === "rush" && field === "question_count" ? "rush_goal" : field))}</label><input id="${bank.id}-${kind}-${field}" data-mode="${kind}" data-field="${field}" type="number" required step="1" min="${field==='question_count'||field==='duration_seconds'?1:0}" max="${field==='duration_seconds'?86400:field==='target_percentage'?100:Math.min(500,bank.question_count)}" value="${mode[field]}" ${kind==='quiz'&&field==='duration_seconds'&&mode.time_mode==='proportional'?'disabled':''}></div>`).join("")}</div>${kind==='quiz'?`<label class="check-label spaced"><input class="proportional-toggle" type="checkbox" ${mode.time_mode==='proportional'?'checked':''}>${esc(t("proportional"))}</label>`:""}</section>`;
}
async function renderAdmin(routeId) {
  if (state.user.role !== "admin") throw {code:"admin_required"};
  const [catalog,audit] = await Promise.all([request("/api/admin/banks"),request("/api/admin/audit")]);
  if (routeId !== state.routeId) return;
  main.innerHTML = `<div class="page-heading"><p class="eyebrow">${esc(t("admin"))}</p><h1>${esc(t("admin_title"))}</h1><p class="muted">${esc(t("admin_subtitle"))}</p></div>
    ${state.user.default_password ? `<div class="callout warning spaced">${esc(t("admin_default_warning"))} <a href="#profile">${esc(t("change_password"))}</a></div>` : ""}
    <div class="admin-upload spaced"><section class="card"><h2>${esc(t("import_bank"))}</h2><label for="bank-file">${esc(t("choose_zip"))}</label><input id="bank-file" type="file" accept=".zip,application/zip"><p class="hint">${esc(t("zip_help"))}</p><button id="validate-bank" class="primary">${esc(t("validate"))}</button><div id="import-preview" class="file-preview"></div></section><section class="card schema-card"><p class="eyebrow">JSON + ZIP</p><h2>${esc(t("schema_kit"))}</h2><p class="muted">${esc(t("schema_help"))}</p><button id="admin-kit">${esc(t("schema_kit"))}</button></section></div>
    <h2>${esc(t("catalog"))}</h2>${catalog.banks.map(bank => `<details class="card bank-config"><summary><span>${esc(text(bank.manifest.title))}<br><small>${esc(bank.manifest.exam_code)} · v${esc(bank.version)} · ${bank.question_count} ${esc(t("questions"))} · ${bank.manifest.languages.join(" / ").toUpperCase()} ${!bank.enabled?' · '+esc(t("disabled")):''}</small></span></summary><div class="config-content"><div class="row between"><h3>${esc(t("configure"))}</h3><button class="export-bank small" data-bank="${esc(bank.id)}">${esc(t("export_bank"))}</button></div><form class="bank-form" data-bank="${esc(bank.id)}"><label class="check-label"><input class="bank-enabled" type="checkbox" ${bank.enabled?'checked':''}>${esc(t("enabled"))}</label><p class="hint">${esc(t("format_help"))}</p><div class="settings-grid">${formatFields(bank,"quiz")}${formatFields(bank,"exam")}${formatFields(bank,"rush")}</div><h3>${esc(t("weights"))}</h3><div class="weights-grid">${bank.manifest.domains.map(domain=>`<div><label for="${bank.id}-weight-${esc(domain.id)}">${esc(text(domain.name))}</label><input id="${bank.id}-weight-${esc(domain.id)}" data-domain="${esc(domain.id)}" type="number" min="0" max="100" step="1" required value="${bank.settings.domain_weights[domain.id]}"></div>`).join("")}</div><p class="hint">${esc(t("weights_help"))}</p><p class="hint">${esc(t("settings_effect"))}</p><div class="form-error hidden callout error-box" role="alert"></div><button type="submit" class="primary spaced">${esc(t("save"))}</button></form></div></details>`).join("") || `<div class="card empty">${esc(t("no_banks"))}</div>`}
    <section class="card spaced"><h2>${esc(t("audit"))}</h2>${audit.items.map(item=>`<div class="audit-row"><strong>${esc(t(item.action))}</strong> · ${esc(item.bank_id)}<br><span class="muted">${esc(item.username || t("system"))} · ${esc(date(item.created_at))}</span></div>`).join("") || "—"}</section>`;
  state.importFile = null; state.importPreview = null;
  $("#admin-kit").onclick = () => download("/api/schema.zip","question-bank-authoring-kit.zip");
  $("#bank-file").onchange = event => { state.importFile = event.target.files[0] || null; state.importPreview = null; $("#import-preview").innerHTML=""; };
  $("#validate-bank").onclick = async event => {
    const button = event.currentTarget; busy(button,true);
    try {
      const file = state.importFile;
      if (!file) throw {code:"validate_first"};
      if (file.size > 10*1024*1024 || !file.size) throw {code:"request_too_large"};
      const preview = await request("/api/admin/banks/validate",file,true);
      if (file !== state.importFile || path() !== "admin") return;
      state.importPreview = preview;
      $("#import-preview").innerHTML = `<div class="callout"><strong>${esc(t("valid_bank"))}</strong>${esc(text(preview.title))} · v${esc(preview.version)}<br>${preview.question_count} ${esc(t("questions"))} · ${preview.languages.join(" / ").toUpperCase()}</div>${preview.replaces?`<div class="callout warning spaced">${esc(t("replace_warning",{version:preview.replaces}))}</div><label class="check-label spaced"><input id="confirm-replace" type="checkbox">${esc(t("confirm_replace"))}</label>`:""}<button id="import-bank" class="primary spaced">${esc(t("import"))}</button>`;
      $("#import-bank").onclick = importBank;
    } catch(error){const el=$("#import-preview");if(el)el.innerHTML=`<div class="callout error-box" role="alert">${esc(errorText(error))}</div>`;}
    finally {busy(button,false);}
  };
  $$(".export-bank").forEach(button=>button.onclick=()=>download(`/api/admin/banks/${button.dataset.bank}/export`,`${button.dataset.bank}.zip`));
  $$(".bank-form").forEach(form=>{
    function syncTime(){
      const proportional=$(".proportional-toggle",form).checked;
      const input=$('[data-mode="quiz"][data-field="duration_seconds"]',form);input.disabled=proportional;
      if(proportional){const count=Number($('[data-mode="quiz"][data-field="question_count"]',form).value),examCount=Number($('[data-mode="exam"][data-field="question_count"]',form).value),seconds=Number($('[data-mode="exam"][data-field="duration_seconds"]',form).value);if(examCount>0)input.value=Math.max(1,Math.round(seconds*count/examCount));}
    }
    $$("input[data-mode],.proportional-toggle",form).forEach(input=>input.addEventListener("input",syncTime));
    form.onsubmit=async event=>{
      event.preventDefault(); const button=$('button[type="submit"]',form),errorBox=$(".form-error",form);busy(button,true);errorBox.classList.add("hidden");
      try{
        syncTime();const settings={quiz:{},exam:{},rush:{},domain_weights:{}};
        $$("input[data-mode]",form).forEach(input=>settings[input.dataset.mode][input.dataset.field]=Number(input.value));
        settings.quiz.time_mode=$(".proportional-toggle",form).checked?"proportional":"fixed";settings.exam.time_mode="fixed";
        $$("input[data-domain]",form).forEach(input=>settings.domain_weights[input.dataset.domain]=Number(input.value));
        await request(`/api/admin/banks/${form.dataset.bank}/configure`,{settings,enabled:$(".bank-enabled",form).checked});toast(t("settings_saved"));
      }catch(error){errorBox.textContent=errorText(error);errorBox.classList.remove("hidden");}finally{busy(button,false);}
    };
  });
}
async function importBank(){
  const button=$("#import-bank");busy(button,true);
  try{
    if(!state.importFile||!state.importPreview)throw{code:"validate_first"};
    const replace=!!state.importPreview.replaces;
    if(replace&&!$("#confirm-replace")?.checked)throw{code:"replacement_confirmation_required"};
    await request(`/api/admin/banks/import${replace?'?replace=1':''}`,state.importFile,true);
    state.importFile=null;state.importPreview=null;toast(t("imported"));renderRoute();
  }catch(error){handleError(error);}finally{busy(button,false);}
}
async function renderRoute(){
  const routeId=++state.routeId;renderHeader();
  if(!state.user){renderAuth();return;}
  const route=path();
  if (route !== state.lastRoute) {
    window.scrollTo(0, 0); state.lastRoute = route;
    clearTimeout(state.toastTimer); $("#toast").classList.add("hidden");
  }
  try{
    if(route.startsWith("attempt/")){
      const id=route.split("/")[1];
      if(state.attempt?.id===id)renderAttempt();else main.innerHTML=`<p class="loading">${esc(t("loading"))}</p>`;
      const result=await request(`/api/attempts/${encodeURIComponent(id)}`);if(routeId!==state.routeId)return;
      acceptAttempt(result);renderAttempt();return;
    }
    main.innerHTML=`<p class="loading">${esc(t("loading"))}</p>`;
    if(route==="profile")renderProfile();
    else if(route==="history")await renderHistory(routeId);
    else if(route==="admin")await renderAdmin(routeId);
    else await renderHome(routeId);
  }catch(error){
    if(routeId!==state.routeId)return;
    if(error.code==="sign_in_required"||error.code==="profile_changed"){handleError(error);return;}
    main.innerHTML=`<div class="card empty"><h2>${esc(errorText(error))}</h2><button id="retry-route">${esc(t("retry"))}</button> <a class="button" href="#home">${esc(t("back_practice"))}</a></div>`;
    $("#retry-route").onclick=renderRoute;
  }
}
async function boot(){
  try{
    const [en,es,session]=await Promise.all([fetch("/locales/en.json").then(r=>r.json()),fetch("/locales/es.json").then(r=>r.json()),request("/api/session")]);
    state.dictionaries={en,es};state.user=session.user;state.registrationOpen=session.registration_open;
    const preferred=state.user?.language||local.get("practice-language")||(navigator.language.startsWith("es")?"es":"en");state.language=["en","es"].includes(preferred)?preferred:"es";
    window.addEventListener("hashchange",renderRoute);window.addEventListener("focus",heartbeat);
    document.addEventListener("visibilitychange",()=>{if(!document.hidden)heartbeat();});
    setInterval(tick,250);setInterval(heartbeat,10000);renderRoute();
  }catch(error){main.innerHTML=`<div class="card empty">Unable to load the local application. Reload the page after checking the server.</div>`;}
}
boot();
