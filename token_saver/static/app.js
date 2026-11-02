"use strict";

const $ = (id) => document.getElementById(id);
const state = {catalog: null, result: null, request: null, comparison: [], comparisonRequest:null, wordData:null, heal: null, busy: false, historyOffset: 0};
const number = (value) => new Intl.NumberFormat("en-US").format(value);
const money = (value) => new Intl.NumberFormat("en-US", {style: "currency", currency: "USD", minimumFractionDigits: value < .01 && value > 0 ? 6 : 2, maximumFractionDigits: value < .01 && value > 0 ? 6 : value < 1 ? 4 : 2}).format(value);
const escapeHTML = (value) => String(value).replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
let toastTimer;
function toast(message) { $("toast").textContent = message; $("toast").hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $("toast").hidden = true, 4500); }
function showError(message) { $("analysis-error").textContent = message; $("analysis-error").hidden = false; }

async function api(path, body, method) {
  let response;
  try { response = await fetch(path, {method: method || (body === undefined ? "GET" : "POST"), headers: body === undefined ? {} : {"Content-Type":"application/json"}, body: body === undefined ? undefined : JSON.stringify(body)}); }
  catch { throw new Error("Cannot reach Token Saver. Start the Python server with start.bat (Windows) or start.sh, then retry."); }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({detail:"The server returned an unreadable response."}));
  if (!response.ok) {
    const message = Array.isArray(data.detail) ? data.detail.map((item) => item.msg).join(" · ") : data.detail;
    throw new Error(message || `Request failed (${response.status}).`);
  }
  return data;
}

function currentModel() { return state.catalog?.models.find((model) => model.id === $("model").value); }
function inputNumber(id) {
  const value = $(id).value;
  if (value === "" || !Number.isFinite(Number(value))) throw new Error(`Enter a valid number for ${$(id).labels?.[0]?.textContent || id}.`);
  return Number(value);
}
function buildRequest() {
  const prompt = $("prompt").value;
  if (!prompt.trim()) throw new Error("Add a prompt to get started.");
  let history = [];
  try { history = JSON.parse($("history-input").value.trim() || "[]"); }
  catch { throw new Error('Conversation history must be a JSON array, for example [{"role":"user","content":"Hello"}].'); }
  if (!Array.isArray(history)) throw new Error("Conversation history must be a JSON array of messages.");
  const request = {prompt, model_id: $("model").value, system_prompt: $("system-prompt").value, history,
    output_low: inputNumber("output-low"), output_expected: inputNumber("output-expected"), output_high: inputNumber("output-high"),
    reasoning_tokens: inputNumber("reasoning"), extra_input_tokens: inputNumber("extra-input"), cached_input_tokens: inputNumber("cached-input"), calls: inputNumber("call-volume"),
    budget_usd: $("budget").value ? inputNumber("budget") : null, count_mode: $("count-mode").value};
  if (request.output_low > request.output_expected || request.output_expected > request.output_high) throw new Error("Response budgets must follow Low ≤ Expected ≤ High.");
  if (request.model_id === "custom") request.custom_model = {name: $("custom-name").value, encoding: $("custom-encoding").value, input_price: inputNumber("custom-in"), output_price: inputNumber("custom-out"), cached_price: null, context_window: inputNumber("custom-context"), max_output: inputNumber("custom-max")};
  return request;
}
function isCurrent(request) { try { return JSON.stringify(buildRequest()) === JSON.stringify(request); } catch { return false; } }
function markStale() {
  if (typeof invalidateOptimizer === "function") invalidateOptimizer();
  updateCharacters();
  invalidateComparison();
  if (state.result) {
    const stale = !isCurrent(state.request);
    $("stale-notice").hidden = !stale;
    $("save-open").disabled = stale;
    $("heal").disabled = stale;
    $("export-json").disabled = stale;
  }
  state.heal = null;
  $("heal-result").hidden = true;
}
function invalidateComparison() {
  state.comparison = []; state.comparisonRequest = null;
  $("export-csv").hidden = true;
  $("comparison-content").innerHTML = '<div class="empty-panel">Compare the current prompt to see updated model costs.</div>';
}
function updateCharacters() {
  const text = $("prompt").value;
  $("char-count").textContent = number([...text].length);
  $("word-count").textContent = number(text.match(/\S+/gu)?.length || 0);
}
function updateModels(selected) {
  const provider = $("provider").value;
  $("model").replaceChildren();
  if (provider === "custom") $("model").add(new Option("Custom model", "custom"));
  else for (const model of state.catalog.models.filter((m) => m.provider === provider)) $("model").add(new Option(model.name, model.id));
  if (selected && [...$("model").options].some((option) => option.value === selected)) $("model").value = selected;
  updateModelInfo();
}
function updateModelInfo() {
  const model = currentModel();
  $("custom-settings").hidden = $("model").value !== "custom";
  const providerOption = $("count-mode").querySelector('[value="provider"]');
  const supportsProvider = !!model?.supports_provider_count;
  providerOption.disabled = !supportsProvider;
  if (!supportsProvider) $("count-mode").value = "local";
  if (model) {
    $("model-info").innerHTML = `<a href="${escapeHTML(model.source)}" target="_blank" rel="noreferrer">Source ↗</a><strong>$${escapeHTML(model.input_price)} input · $${escapeHTML(model.output_price)} output</strong> / 1M tokens<br>${number(model.context_window)} ${model.context_kind === "input" ? "input" : "context"} limit · ${model.encoding ? "Local tokenizer" : "Approximate locally"}${model.status !== "Available" ? `<span class="model-status">${escapeHTML(model.status)}</span>` : ""}`;
    const configured = state.catalog.provider_counting[model.provider];
    $("provider-help").textContent = supportsProvider ? (configured ? "Provider key configured. Provider mode sends your supplied text to this provider for input counting." : `Set ${model.provider === "google" ? "GEMINI_API_KEY" : "ANTHROPIC_API_KEY"} on the server to enable provider counting. Local estimates work without a key.`) : model.provider === "groq" ? "Groq analysis uses approximate local counts and needs no key. Exact token boundaries are unavailable here. GROQ_API_KEY is used only when you request an AI rewrite." : "This preset uses local counting. Extra platform overhead is still estimated.";
  } else $("model-info").textContent = "Enter the rates and limits for your platform. A chosen encoding is only accurate if it matches your model.";
  updatePrivacy();
}
function updatePrivacy() { $("privacy-caption").textContent = $("count-mode").value === "provider" ? "↗ Provider mode sends text to your selected provider." : "◈ Local analysis keeps your prompt on this computer. AI optimization is a separate cloud action."; }
function setPage(name) {
  document.querySelectorAll(".page").forEach((page) => { page.hidden = page.id !== `page-${name}`; page.classList.toggle("active", !page.hidden); });
  document.querySelectorAll(".nav-item").forEach((button) => { button.classList.toggle("active", button.dataset.page === name); button.setAttribute("aria-current", button.dataset.page === name ? "page" : "false"); });
  $("page-label").textContent = {analyzer:"Prompt analyzer", compare:"Model comparison", optimizer:"AI optimizer", history:"Saved analyses", guide:"How it works"}[name];
  if (name === "optimizer") openOptimizer();
  if (name === "history") loadHistory();
  if (name === "compare" && $("prompt").value.trim()) runComparison();
  window.scrollTo({top:0, behavior:"instant"});
}

async function runAnalysis() {
  if (state.busy) return;
  let request;
  try { request = buildRequest(); } catch (error) { showError(error.message); $("prompt").focus(); return; }
  state.busy = true;
  $("analyze").disabled = true;
  $("analyze").firstElementChild.textContent = request.count_mode === "provider" ? "Counting with provider…" : "Analyzing…";
  $("analysis-error").hidden = true;
  try {
    const result = await api("/api/analyze", request);
    if (!isCurrent(request)) { toast("Inputs changed while analyzing. Run analysis again."); return; }
    state.result = result; state.request = request; state.heal = null;
    renderResults(result);
    $("results").scrollIntoView({behavior:window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block:"start"});
  } catch (error) { showError(error.message); }
  finally { state.busy = false; $("analyze").disabled = false; $("analyze").firstElementChild.textContent = "Analyze prompt"; }
}

function renderResults(result) {
  ++wordVersion;
  $("empty-results").hidden = true; $("results").hidden = false; $("stale-notice").hidden = true; $("heal-result").hidden = true;
  $("heal-suggestions").textContent = "Code, quotes and structured content are protected from automatic edits.";
  $("word-search").value = ""; $("word-multiple").checked = false;
  renderWords(result.word_preview);
  for (const id of ["save-open", "heal", "export-json"]) $(id).disabled = false;
  const {counting, scenarios, volume, context} = result;
  $("count-badge").textContent = {local_tokenizer:"TEXT COUNTED · TOTAL ESTIMATED",heuristic:"APPROXIMATE INPUT",provider_count:"PROVIDER INPUT COUNT"}[counting.method];
  $("metric-input").textContent = number(counting.input_tokens);
  $("metric-input-note").textContent = counting.method === "provider_count" ? "Provider count + your extra allowance" : counting.method === "heuristic" ? "Heuristic · actual count may differ" : `${number(counting.text_tokens)} text + formatting / extras`;
  $("metric-output").textContent = number(scenarios.expected.billed_output_tokens);
  $("metric-output-note").textContent = `${number(scenarios.expected.visible_output_tokens)} response + ${number(result.reasoning_tokens)} reasoning`;
  $("metric-cost").textContent = money(scenarios.expected.total_usd);
  $("metric-cost-note").textContent = `${money(scenarios.low.total_usd)} – ${money(scenarios.high.total_usd)} by response budget`;
  $("metric-volume-label").textContent = `AT ${number(volume.calls)} CALLS`;
  $("metric-volume").textContent = money(volume.total_usd);
  $("metric-budget").textContent = volume.budget_usd ? (volume.calls_within_budget === null ? "Zero-cost scenario; no finite budget limit" : `${number(volume.calls_within_budget)} calls within ${money(volume.budget_usd)}`) : "At your expected response budget.";
  $("total-label").textContent = `${number(scenarios.expected.total_tokens)} total`;
  const parts = counting.method === "provider_count" ? [
    ["Provider input",counting.base_input_tokens,"#a8c17f"],["Extra input",counting.extra_input_tokens,"#e4c39f"],["Visible output",scenarios.expected.visible_output_tokens,"#c5b7df"],["Reasoning",result.reasoning_tokens,"#a7c8ce"]
  ] : [["Prompt",counting.breakdown.prompt,"#a8c17f"],["System + history",counting.breakdown.system + counting.breakdown.history,"#cfdda9"],["Formatting + extras",counting.overhead_tokens + counting.extra_input_tokens,"#e4c39f"],["Visible output",scenarios.expected.visible_output_tokens,"#c5b7df"],["Reasoning",result.reasoning_tokens,"#a7c8ce"]];
  $("token-bar").replaceChildren(); $("breakdown-legend").replaceChildren();
  for (const [label,value,color] of parts) {
    if (value) { const segment = document.createElement("span"); segment.style.flex = String(value); segment.style.background = color; segment.title = `${label}: ${number(value)}`; $("token-bar").append(segment); }
    const item = document.createElement("div"); item.className = "legend-item"; item.innerHTML = `<span class="color-dot" style="background:${color}"></span>${label}<strong>${number(value)}</strong>`; $("breakdown-legend").append(item);
  }
  $("context-box").className = `context-box${context.fits ? "" : " exceeded"}`;
  $("context-box").innerHTML = `<div><span>${context.fits ? "Within" : "Exceeds"} model limits · ${context.kind === "input" ? "input only" : "high output scenario included"}</span><strong>${context.percent}%</strong></div><div class="context-meter"><span style="width:${Math.min(100, context.percent)}%"></span></div><p class="field-help">${number(context.used)} / ${number(context.limit)} ${context.kind === "input" ? "input" : "context"} tokens · ${number(context.max_output)} maximum output</p>`;
  $("scenario-table").innerHTML = `<table><thead><tr><th>Scenario</th><th>Output incl. reasoning</th><th>Cost / call</th></tr></thead><tbody>${Object.entries(scenarios).map(([name,scenario]) => `<tr><td>${name[0].toUpperCase()+name.slice(1)}</td><td>${number(scenario.billed_output_tokens)}</td><td>${money(scenario.total_usd)}</td></tr>`).join("")}</tbody></table>`;
  $("encoding-label").textContent = result.token_preview?.encoding || "PROVIDER TOKENIZER NOT BUNDLED";
  $("token-preview").replaceChildren();
  if (result.token_preview?.available) {
    for (const item of result.token_preview.tokens) {
      const token = document.createElement("span"); token.className = `token${item.byte_fragment ? " byte-fragment" : ""}`;
      token.textContent = item.text.replaceAll(" ", "·").replaceAll("\n", "↵\n").replaceAll("\t", "⇥");
      token.title = `Token ID ${item.id}${item.byte_fragment ? " · UTF-8 byte fragment (hex)" : ""}`;
      token.tabIndex = 0; token.setAttribute("aria-label", `${token.title}: ${token.textContent}`); $("token-preview").append(token);
    }
    $("preview-note").textContent = result.token_preview.truncated ? `Showing the first 400 of ${number(result.token_preview.total)} prompt tokens. Full text was counted.` : "Prompt text only. Spaces are shown as · and line breaks as ↵. System and history counts are included above.";
  } else {
    $("token-preview").textContent = "Token boundaries are unavailable for this model. Local mode supplies a rough count. Provider count APIs, where supported, return totals without token IDs.";
    $("preview-note").textContent = counting.sensitivity ? `Input sensitivity: ${number(counting.sensitivity.low)}–${number(counting.sensitivity.high)} tokens. This ±35% what-if band is not a confidence interval; actual counts may fall outside it.` : "Per-section counts remain local estimates even when provider counting is selected.";
  }
  $("warnings").replaceChildren(); for (const warning of result.warnings) { const item=document.createElement("li"); item.textContent=warning; $("warnings").append(item); }
  $("pricing-source").innerHTML = `Catalog checked ${escapeHTML(result.pricing.verified_on)}. ${escapeHTML(result.pricing.basis)} ${result.model.source ? `<a href="${escapeHTML(result.model.source)}" target="_blank" rel="noreferrer">View model pricing ↗</a>` : "Custom rates supplied by you."}`;
}

function renderWords(data) {
  state.wordData = data;
  $("word-controls").hidden = !data?.available;
  $("word-pagination").hidden = !data?.available || data.matching_words <= data.limit;
  $("word-method").textContent = data?.available ? data.encoding : "WORD COUNTS UNAVAILABLE";
  if (!data?.available) {
    $("word-summary").textContent = "Exact word counts need the selected model’s tokenizer.";
    $("word-table").textContent = data?.reason || "Word breakdown is unavailable.";
    $("word-note").textContent = "A provider-reported total does not reveal how individual words were tokenized.";
    return;
  }
  $("word-summary").textContent = `${number(data.total_words)} words · ${number(data.prompt_tokens)} prompt tokens · ${number(data.whitespace_only_tokens)} whitespace-only tokens${data.shared_tokens ? ` · ${number(data.shared_tokens)} tokens shared by words` : ""}`;
  $("word-table").innerHTML = data.words.length ? `<table><thead><tr><th>#</th><th>Word</th><th>Tokens</th><th>Token pieces · hover for ID</th></tr></thead><tbody>${data.words.map((row)=>`<tr><td>${row.number}</td><td class="word-text">${escapeHTML(row.word)}</td><td><span class="word-count${row.token_count>1?" multiple":""}">${row.token_count}</span></td><td><div class="word-pieces">${row.pieces.map((piece)=>`<span class="word-piece${piece.shared?" shared":""}" tabindex="0" title="Token ${piece.id} · position ${piece.position+1}${piece.byte_fragment?" · UTF-8 bytes in hex":""}${piece.shared?" · shared with another word":""}">${escapeHTML(piece.text.replaceAll(" ","·").replaceAll("\n","↵").replaceAll("\t","⇥"))}</span>`).join("")}</div></td></tr>`).join("")}</tbody></table>` : '<div class="empty-panel">No words match these filters.</div>';
  $("word-page-label").textContent = `${data.words.length ? data.offset+1 : 0}–${data.offset+data.words.length} of ${number(data.matching_words)} matching words`;
  $("word-previous").disabled = data.offset === 0;
  $("word-next").disabled = !data.has_more;
  $("word-note").textContent = data.note + " Spaces in token pieces are shown as ·. Very long words show at most 64 pieces, but their full token count is retained. This table covers the prompt; system instructions and history are counted separately above.";
}
let wordVersion = 0;
async function loadWords(offset=0) {
  if (!state.request || !isCurrent(state.request)) return toast("Analyze the updated prompt before inspecting words.");
  const version = ++wordVersion;
  const request = structuredClone(state.request);
  const query = $("word-search").value;
  const minTokens = $("word-multiple").checked ? 2 : 0;
  try {
    const data = await api("/api/words", {prompt:request.prompt,model_id:request.model_id,custom_model:request.custom_model || null,offset,limit:100,query,min_tokens:minTokens});
    if (version !== wordVersion || !isCurrent(request) || query !== $("word-search").value || minTokens !== ($("word-multiple").checked ? 2 : 0)) return;
    renderWords(data);
  } catch(error) {toast(error.message);}
}

async function runHealing() {
  if (!state.request || !isCurrent(state.request)) return toast("Analyze the current prompt first.");
  const request = structuredClone(state.request);
  const shorten = $("shorten-phrases").checked;
  $("heal").disabled = true; $("heal").textContent = "Finding improvements…";
  try {
    const result = await api("/api/heal", {prompt:request.prompt,model_id:request.model_id, custom_model:request.custom_model || null, shorten_phrases:shorten});
    if (!isCurrent(request)) return toast("Prompt changed. Analyze it again before healing.");
    state.heal = result;
    $("heal-result").hidden = false; $("saved-tokens").textContent = number(result.saved_tokens); $("saved-percent").textContent = `${result.saved_percent}% ${result.method === "heuristic" ? "estimated reduction" : "reduction"}`;
    $("healed-prompt").value = result.healed;
    $("heal-changes").replaceChildren(); for (const change of result.changes) {const item=document.createElement("li"); item.textContent=change; $("heal-changes").append(item);}
    $("heal-suggestions").textContent = result.suggestions.join(" ");
    $("apply-heal").disabled = result.saved_tokens === 0;
  } catch(error) {toast(error.message);} finally {$("heal").disabled = !isCurrent(request); $("heal").textContent = "✳  Find improvements";}
}

async function runComparison() {
  invalidateComparison();
  let request;
  try {request=buildRequest();} catch(error) {$("comparison-content").innerHTML = `<div class="empty-panel">${escapeHTML(error.message)} Add it in Prompt analyzer, then compare.</div>`;return;}
  $("compare-refresh").disabled=true; $("compare-refresh").textContent="Comparing…";
  try {
    const result=await api("/api/compare",request);
    if(!isCurrent(request)) return toast("Inputs changed. Refresh the comparison.");
    state.comparison=result.models; state.comparisonRequest=structuredClone(request);
    const largest=Math.max(...result.models.map((model)=>model.cost_usd || 0),.00000001);
    $("comparison-content").innerHTML=`<div class="table-wrap"><table><thead><tr><th>Model / provider</th><th>Input tokens</th><th>Cost / call</th><th>${number(request.calls)} calls</th><th>Limits</th><th></th></tr></thead><tbody>${result.models.map((row)=>`<tr class="${row.model.id===request.model_id ? "selected-row" : ""}"><td><strong>${escapeHTML(row.model.name)}</strong><small>${escapeHTML(row.model.provider_name)} · ${escapeHTML(row.model.status)}</small></td>${row.error ? `<td colspan="4">${escapeHTML(row.error)}</td>` : `<td>${number(row.input_tokens)}<small>${row.method==="heuristic"?"Approximate":"Text counted + allowance"}</small></td><td>${money(row.cost_usd)}<div class="comparison-bar"><span style="width:${Math.max(2,row.cost_usd/largest*100)}%"></span></div></td><td>${money(row.volume_usd)}</td><td>${row.fits?"Within limits":"Exceeds limits"}</td>`}<td><button class="button secondary small" data-select-model="${escapeHTML(row.model.id)}">Select ↗</button></td></tr>`).join("")}</tbody></table></div>`;
    $("export-csv").hidden=false;
  } catch(error) {$("comparison-content").innerHTML=`<div class="empty-panel">${escapeHTML(error.message)}</div>`;}
  finally {$("compare-refresh").disabled=false;$("compare-refresh").textContent="Compare current prompt ↗";}
}

function download(name, content, type) {
  const url=URL.createObjectURL(new Blob([content],{type}));
  const link=document.createElement("a");link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function exportCSV() {
  if(!state.comparisonRequest || !isCurrent(state.comparisonRequest) || !state.comparison.length) return toast("Refresh the comparison before exporting.");
  const cell=(value)=>`"${String(value ?? "").replace(/^[=+@-]/,"'$&").replaceAll('"','""')}"`;
  const rows=[["Provider","Model","Input tokens","Counting method","USD per call","USD at selected volume","Within limits"]];
  for(const row of state.comparison) rows.push([row.model.provider_name,row.model.name,row.input_tokens,row.method,row.cost_usd,row.volume_usd,row.fits]);
  download("token-saver-comparison.csv",rows.map((row)=>row.map(cell).join(",")).join("\r\n"),"text/csv;charset=utf-8");
}
function restoreRequest(request) {
  const model=state.catalog.models.find((item)=>item.id===request.model_id);
  $("provider").value=request.model_id==="custom"?"custom":model?.provider || "openai";updateModels(request.model_id);
  $("prompt").value=request.prompt;$("system-prompt").value=request.system_prompt;$("history-input").value=request.history.length?JSON.stringify(request.history,null,2):"";
  const mapping={"output-low":"output_low","output-expected":"output_expected","output-high":"output_high","reasoning":"reasoning_tokens","extra-input":"extra_input_tokens","cached-input":"cached_input_tokens","call-volume":"calls","budget":"budget_usd"};
  for(const [id,key] of Object.entries(mapping)) $(id).value=request[key] ?? "";
  if(request.custom_model){const custom=request.custom_model;$("custom-name").value=custom.name;$("custom-encoding").value=custom.encoding;$("custom-in").value=custom.input_price;$("custom-out").value=custom.output_price;$("custom-context").value=custom.context_window;$("custom-max").value=custom.max_output;}
  // A history click never silently sends an old prompt to a provider.
  $("count-mode").value="local";updatePrivacy();updateCharacters();markStale();
  document.querySelectorAll("[data-size]").forEach((button)=>button.classList.remove("selected"));
}
let historyVersion=0;
async function loadHistory(more=false) {
  const version=++historyVersion;
  const offset=more ? state.historyOffset : 0;
  const query=$("history-search").value;
  $("history-more").disabled=true;
  try {
    const data=await api(`/api/history?q=${encodeURIComponent(query)}&limit=20&offset=${offset}`);
    if(version!==historyVersion)return;
    if(!more)$("history-content").replaceChildren();
    if(!data.items.length&&!more)$("history-content").innerHTML='<div class="card empty-panel">No saved analyses yet. Analyze a prompt and choose Save analysis to start your library.</div>';
    for(const entry of data.items){
      const article=document.createElement("article");article.className="card history-entry";
      article.innerHTML=`<h2>${escapeHTML(entry.title)}</h2><span class="history-date">${escapeHTML(new Date(entry.created_at).toLocaleString())}</span><span class="history-model">${escapeHTML(entry.model)}</span><div class="history-stats"><span>${number(entry.input_tokens)} input tokens</span><strong>${money(entry.cost_usd)} / call</strong></div><div class="history-actions"><button class="button secondary small" data-restore="${entry.id}">Open & recalculate ↗</button><button class="text-button delete-button" data-delete="${entry.id}">Delete</button></div>`;
      $("history-content").append(article);
    }
    state.historyOffset=offset+data.items.length;$("history-more").hidden=data.items.length<20;
  }catch(error){toast(error.message);}finally{$("history-more").disabled=false;}
}

const EXAMPLE="Please write a helpful onboarding email in order to welcome new users to a personal finance app.\n\n\nThe audience is university students who want to build better saving habits.  Keep the tone friendly, practical, and encouraging.\n\nFor the purpose of making the next step clear, include one call to action to create their first savings goal.  Due to the fact that readers are busy, keep the email under 150 words.\n\nReturn a subject line and the email body. Do not invent product features or make financial promises.";
function loadExample(){setPage("analyzer");$("prompt").value=EXAMPLE;markStale();$("prompt").focus();toast("Example loaded. Choose a model and analyze.");}

document.querySelectorAll(".nav-item").forEach((button)=>button.addEventListener("click",()=>setPage(button.dataset.page)));
$("provider").addEventListener("change",()=>{updateModels();markStale();});
$("model").addEventListener("change",()=>{updateModelInfo();markStale();});
$("count-mode").addEventListener("change",updatePrivacy);
document.querySelectorAll("#page-analyzer input,#page-analyzer select,#page-analyzer textarea").forEach((input)=>input.addEventListener("input",()=>{if(!["healed-prompt","upload","shorten-phrases","word-search","word-multiple"].includes(input.id))markStale();}));
let wordSearchTimer;
$("word-search").addEventListener("input",()=>{clearTimeout(wordSearchTimer);wordSearchTimer=setTimeout(()=>loadWords(),200);});
$("word-multiple").addEventListener("change",()=>loadWords());
$("word-next").addEventListener("click",()=>loadWords((state.wordData?.offset || 0)+100));
$("word-previous").addEventListener("click",()=>loadWords(Math.max(0,(state.wordData?.offset || 0)-100)));
$("shorten-phrases").addEventListener("change",()=>{$("heal-result").hidden=true;state.heal=null;});
document.querySelectorAll("[data-size]").forEach((button)=>button.addEventListener("click",()=>{const sizes={short:[64,128,256],balanced:[256,512,1024],detailed:[1024,2048,4096]};["output-low","output-expected","output-high"].forEach((id,index)=>$(id).value=sizes[button.dataset.size][index]);document.querySelectorAll("[data-size]").forEach((item)=>item.classList.toggle("selected",item===button));markStale();}));
for(const id of ["output-low","output-expected","output-high"])$(id).addEventListener("input",()=>document.querySelectorAll("[data-size]").forEach((button)=>button.classList.remove("selected")));
$("analyze").addEventListener("click",runAnalysis);
$("load-example").addEventListener("click",loadExample);$("example-sidebar").addEventListener("click",loadExample);
$("clear-prompt").addEventListener("click",()=>{$("prompt").value="";markStale();$("prompt").focus();});
document.addEventListener("keydown",(event)=>{if((event.ctrlKey||event.metaKey)&&event.key==="Enter"&&!$("page-analyzer").hidden){event.preventDefault();runAnalysis();}});
$("upload").addEventListener("change",async()=>{const file=$("upload").files[0];if(!file)return;try{if(file.size>400000)throw new Error("Import a UTF-8 text file smaller than 400 KB.");const text=new TextDecoder("utf-8",{fatal:true}).decode(await file.arrayBuffer());if([...text].length>100000)throw new Error("The prompt must be at most 100,000 characters.");$("prompt").value=text;markStale();toast(`Imported ${file.name}`);}catch(error){toast(error.message);}finally{$("upload").value="";}});
$("heal").addEventListener("click",runHealing);
$("apply-heal").addEventListener("click",()=>{if(!state.heal||!isCurrent(state.request))return toast("Analyze the current prompt before applying edits.");const prompt=state.heal.healed;$("prompt").value=prompt;markStale();runAnalysis();});
$("copy-heal").addEventListener("click",async()=>{try{await navigator.clipboard.writeText($("healed-prompt").value);toast("Proposed prompt copied.");}catch{$("healed-prompt").focus();$("healed-prompt").select();toast("Select and copy the proposed prompt manually.");}});
$("export-json").addEventListener("click",()=>{if(!state.result||!isCurrent(state.request))return toast("Re-analyze before exporting.");download("token-saver-analysis.json",JSON.stringify({request:state.request,result:state.result},null,2),"application/json");});
$("compare-refresh").addEventListener("click",runComparison);$("export-csv").addEventListener("click",exportCSV);
$("comparison-content").addEventListener("click",(event)=>{const button=event.target.closest("[data-select-model]");if(!button)return;const model=state.catalog.models.find((item)=>item.id===button.dataset.selectModel);$("provider").value=model?.provider || "custom";updateModels(button.dataset.selectModel);markStale();setPage("analyzer");runAnalysis();});
$("save-open").addEventListener("click",()=>{if(!state.result||!isCurrent(state.request))return toast("Re-analyze before saving.");$("save-title").value=Array.from(state.request.prompt).slice(0,65).join("").replace(/\s+/g," ");$("save-dialog").showModal();});
for(const id of ["close-save","cancel-save"])$(id).addEventListener("click",()=>$("save-dialog").close());
$("save-form").addEventListener("submit",async(event)=>{event.preventDefault();if(!isCurrent(state.request)){toast("Inputs changed. Re-analyze before saving.");return;}$("save-submit").disabled=true;try{await api("/api/history",{title:$("save-title").value.trim()||"Untitled analysis",request:state.request});$("save-dialog").close();toast("Analysis saved to your local library.");}catch(error){toast(error.message);}finally{$("save-submit").disabled=false;}});
$("history-refresh").addEventListener("click",()=>loadHistory());$("history-more").addEventListener("click",()=>loadHistory(true));
let searchTimer;$("history-search").addEventListener("input",()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>loadHistory(),250);});
$("history-content").addEventListener("click",async(event)=>{const restore=event.target.closest("[data-restore]");const remove=event.target.closest("[data-delete]");try{if(restore){const record=await api(`/api/history/${restore.dataset.restore}`);restoreRequest(record.request);setPage("analyzer");await runAnalysis();toast("Saved prompt restored and recalculated locally with current catalog rates.");}if(remove){if(remove.dataset.confirm!=="yes"){remove.dataset.confirm="yes";remove.textContent="Confirm delete";setTimeout(()=>{if(remove.isConnected){delete remove.dataset.confirm;remove.textContent="Delete";}},4000);return;}await api(`/api/history/${remove.dataset.delete}`,undefined,"DELETE");await loadHistory();toast("Saved analysis deleted.");}}catch(error){toast(error.message);}});

async function initialize(){
  try{
    state.catalog=await api("/api/models");
    $("provider").replaceChildren();
    const seen=new Set();for(const model of state.catalog.models){if(!seen.has(model.provider)){$("provider").add(new Option(model.provider_name,model.provider));seen.add(model.provider);}}
    $("provider").add(new Option("Custom / other platform","custom"));updateModels("gpt-5.4-mini");$("model").disabled=false;$("analyze").disabled=false;
    $("catalog-date").textContent=`Rates checked ${state.catalog.verified_on}`;
    $("guide-sources").innerHTML='<a href="https://developers.openai.com/api/docs/pricing" target="_blank" rel="noreferrer">OpenAI pricing ↗</a><a href="https://platform.claude.com/docs/en/about-claude/pricing" target="_blank" rel="noreferrer">Anthropic pricing ↗</a><a href="https://ai.google.dev/gemini-api/docs/pricing" target="_blank" rel="noreferrer">Google pricing ↗</a><a href="https://console.groq.com/docs/models" target="_blank" rel="noreferrer">Groq models & pricing ↗</a><a href="https://github.com/openai/tiktoken" target="_blank" rel="noreferrer">tiktoken ↗</a>';
  }catch(error){showError(`Could not load the model catalog. ${error.message} Refresh after starting the Python server.`);}
}
initialize();
