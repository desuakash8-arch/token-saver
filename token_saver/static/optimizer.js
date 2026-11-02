"use strict";

const aiState = {config:null, result:null, snapshot:null, busy:false, version:0, undo:null};
function syncUndo() {
  const available=!!aiState.undo && $("prompt").value===aiState.undo.applied;
  $("ai-undo").hidden=!available; $("ai-undo-analyzer").hidden=!available;
}
function invalidateOptimizer() {
  aiState.version++; aiState.result=null; aiState.snapshot=null;
  $("ai-result").hidden=true; $("ai-error").hidden=true;
  if(aiState.undo && $("prompt").value!==aiState.undo.applied) aiState.undo=null;
  syncUndo();
}
function openOptimizer() {
  $("ai-original").value=$("prompt").value;
  $("ai-target").textContent=currentModel()?.name || ($("model").value==="custom" ? $("custom-name").value : "Choose a target model");
  syncUndo(); checkOptimizer();
}
async function checkOptimizer() {
  try {
    aiState.config=await api("/api/optimizer");
    $("ai-connection").textContent=aiState.config.configured ? "" : "AI optimization needs GROQ_API_KEY in the project's .env file. Restart Token Saver after adding it.";
  } catch(error) { aiState.config=null; $("ai-connection").textContent=error.message; }
  $("ai-connection").hidden=!!aiState.config?.configured;
  $("ai-check").hidden=!!aiState.config?.configured;
  $("ai-optimize").disabled=aiState.busy || !aiState.config?.configured;
}
function optimizerCurrent() {
  const snapshot=aiState.snapshot;
  return snapshot && isCurrent(snapshot.request) && snapshot.optimizer_model===$("ai-model").value && snapshot.keep_exact===$("ai-keep").value;
}
function aiList(id, items, empty) {
  const list=$(id); list.replaceChildren();
  for(const text of items.length ? items : [empty]) {const item=document.createElement("li");item.textContent=text;list.append(item);}
}
function renderOptimization(result) {
  $("ai-result").hidden=false;
  $("ai-verdict").textContent=result.accepted ? "REVIEW BEFORE APPLYING" : "ORIGINAL KEPT";
  $("ai-before").textContent=number(result.before_tokens); $("ai-after").textContent=number(result.after_tokens);
  $("ai-saved").textContent=number(result.saved_tokens); $("ai-percent").textContent=`${result.saved_percent}% less prompt input`;
  $("ai-count-method").textContent=result.method==="heuristic" ? "approximate target tokens" : "counted with target tokenizer";
  $("ai-proposal").value=result.optimized_prompt;
  aiList("ai-changes",result.changes,"No rewrite applied."); aiList("ai-requirements",result.requirements,"Review every original requirement yourself."); aiList("ai-warnings",result.warnings,"Review the rewrite before applying.");
  const optimizer=result.optimizer, economy=result.economics;
  const usage=optimizer.usage ? `${number(optimizer.usage.prompt_tokens)} input + ${number(optimizer.usage.completion_tokens)} output tokens` : "usage unavailable";
  const cost=optimizer.estimated_cost_usd===null ? "unknown" : money(optimizer.estimated_cost_usd);
  const net=economy.net_saving_usd===null ? "unknown" : money(economy.net_saving_usd);
  $("ai-economics").textContent=`Groq editor: ${usage}; estimated cost ${cost}. Target input savings: ${money(economy.input_saving_per_call_usd)} per call. Break-even: ${economy.break_even_calls===null ? "not established" : number(economy.break_even_calls)+" uses"}. Estimated net savings over ${number(economy.calls)} uses: ${net}. ${economy.basis}`;
  $("ai-apply").disabled=!result.accepted;
  $("ai-result").scrollIntoView({behavior:"smooth",block:"start"});
}
async function runOptimizer() {
  if(aiState.busy)return;
  invalidateOptimizer();
  let snapshot;
  try {
    snapshot={request:buildRequest(),optimizer_model:$("ai-model").value,keep_exact:$("ai-keep").value};
    if([...snapshot.request.prompt].length>20000)throw new Error("AI optimization supports prompts up to 20,000 characters.");
    if(snapshot.keep_exact.split(/\r?\n/).some(line=>line.trim()&&!snapshot.request.prompt.includes(line.trim())))throw new Error("Each protected snippet must already appear exactly in your prompt.");
  } catch(error) {$("ai-error").textContent=error.message;$("ai-error").hidden=false;return;}
  const version=aiState.version;
  aiState.busy=true; $("ai-optimize").disabled=true; $("ai-optimize").textContent="Optimizing prompt…";
  try {
    const result=await api("/api/optimize",snapshot);
    if(version!==aiState.version || !isCurrent(snapshot.request))return toast("Inputs changed while Groq was working. The rewrite was discarded; the API call may still be charged.");
    aiState.result=result; aiState.snapshot=structuredClone(snapshot);renderOptimization(result);
  } catch(error) {$("ai-error").textContent=error.message;$("ai-error").hidden=false;}
  finally {aiState.busy=false;$("ai-optimize").disabled=!aiState.config?.configured;$("ai-optimize").textContent="Optimize prompt ↗";}
}
function applyOptimization() {
  if(!aiState.result?.accepted || !optimizerCurrent())return toast("Optimize the current prompt before applying a rewrite.");
  const undo={original:$("prompt").value,applied:aiState.result.optimized_prompt};
  $("prompt").value=undo.applied;$("count-mode").value="local";updatePrivacy();markStale();
  aiState.undo=undo;syncUndo();setPage("analyzer");runAnalysis();
}
function undoOptimization() {
  if(!aiState.undo || $("prompt").value!==aiState.undo.applied)return toast("The prompt has changed; undo is no longer available.");
  $("prompt").value=aiState.undo.original; aiState.undo=null;$("count-mode").value="local";updatePrivacy();markStale();setPage("analyzer");runAnalysis();toast("Original prompt restored.");
}
$("open-optimizer").addEventListener("click",()=>setPage("optimizer"));
$("ai-edit").addEventListener("click",()=>{setPage("analyzer");$("prompt").focus();});
$("ai-check").addEventListener("click",checkOptimizer);
$("ai-model").addEventListener("change",invalidateOptimizer);
$("ai-keep").addEventListener("input",invalidateOptimizer);
$("ai-optimize").addEventListener("click",runOptimizer);
$("ai-apply").addEventListener("click",applyOptimization);
$("ai-undo").addEventListener("click",undoOptimization);
$("ai-undo-analyzer").addEventListener("click",undoOptimization);
$("ai-copy").addEventListener("click",async()=>{
  if(!optimizerCurrent())return toast("Optimize the current prompt before copying.");
  try {await navigator.clipboard.writeText(aiState.result.optimized_prompt);toast("Rewrite copied.");}
  catch {$("ai-proposal").focus();$("ai-proposal").select();toast("Select and copy the rewrite manually.");}
});
$("ai-export").addEventListener("click",()=>{
  if(!optimizerCurrent())return toast("Optimize the current prompt before exporting.");
  download("token-saver-ai-rewrite.json",JSON.stringify(aiState.result,null,2),"application/json");
});
