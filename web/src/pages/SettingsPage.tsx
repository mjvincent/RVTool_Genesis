import { useState, useEffect } from 'react';
import {
  Button,
  TextInput,
  PasswordInput,
  RadioButtonGroup,
  RadioButton,
  InlineNotification,
  InlineLoading,
  Tag,
  Select,
  SelectItem,
} from '@carbon/react';
import { Settings as SettingsIcon } from '@carbon/icons-react';
import {
  api, LLMProvider, LLMSettingsResponse, LLMSettingsSave, ModelRecommendation,
  LocalAdvisorResponse, BenchmarkResult, BackendType, DiscoveredModel, DiscoveryResponse,
} from '../api/client';

// ─── defaults ────────────────────────────────────────────────────────────────
const DEFAULTS = {
  ollama_base_url: 'http://host.docker.internal:11434',
  ollama_model: 'phi4-mini',
  watsonx_url: 'https://us-south.ml.cloud.ibm.com',
  watsonx_model: 'ibm/granite-3-8b-instruct',
  openai_base_url: 'https://api.openai.com',
  openai_model: 'gpt-4o-mini',
  anthropic_model: 'claude-3-haiku-20240307',
};

const WATSONX_MODELS = [
  'ibm/granite-3-8b-instruct',
  'ibm/granite-3-2b-instruct',
  'meta-llama/llama-3-3-70b-instruct',
  'meta-llama/llama-3-1-8b-instruct',
];
const OPENAI_MODELS = ['gpt-4o-mini', 'gpt-4o', 'gpt-4-turbo'];
const ANTHROPIC_MODELS = [
  'claude-3-haiku-20240307',
  'claude-3-5-sonnet-20241022',
  'claude-3-opus-20240229',
];

// ─── component ───────────────────────────────────────────────────────────────
export default function SettingsPage() {
  const [loaded, setLoaded] = useState(false);
  const [provider, setProvider] = useState<LLMProvider>('ollama');

  // Ollama
  const [ollamaUrl, setOllamaUrl] = useState(DEFAULTS.ollama_base_url);
  const [ollamaModel, setOllamaModel] = useState(DEFAULTS.ollama_model);

  // watsonx.ai
  const [wxKey, setWxKey] = useState('');
  const [wxKeyHint, setWxKeyHint] = useState<string | null>(null);
  const [wxProjectId, setWxProjectId] = useState('');
  const [wxUrl, setWxUrl] = useState(DEFAULTS.watsonx_url);
  const [wxModel, setWxModel] = useState(DEFAULTS.watsonx_model);

  // OpenAI
  const [oaiKey, setOaiKey] = useState('');
  const [oaiKeyHint, setOaiKeyHint] = useState<string | null>(null);
  const [oaiBaseUrl, setOaiBaseUrl] = useState(DEFAULTS.openai_base_url);
  const [oaiModel, setOaiModel] = useState(DEFAULTS.openai_model);

  // Anthropic
  const [antKey, setAntKey] = useState('');
  const [antKeyHint, setAntKeyHint] = useState<string | null>(null);
  const [antModel, setAntModel] = useState(DEFAULTS.anthropic_model);

  // Docker Model Runner
  const [dmrBaseUrl, setDmrBaseUrl] = useState('http://host.docker.internal:9545');
  const [dmrModel, setDmrModel] = useState('');

  // Model recommendation state
  const [recommendation, setRecommendation] = useState<ModelRecommendation | null>(null);
  const [previousModel, setPreviousModel] = useState<string | null>(null);
  const [recLoading, setRecLoading] = useState(false);

  // Local Advisor state
  const [advisor, setAdvisor] = useState<LocalAdvisorResponse | null>(null);
  const [advisorLoading, setAdvisorLoading] = useState(false);
  const [advisorError, setAdvisorError] = useState('');

  // Discover Models state
  const [discoverOpen, setDiscoverOpen] = useState(false);
  const [discoverLoading, setDiscoverLoading] = useState(false);
  const [discoverResult, setDiscoverResult] = useState<DiscoveryResponse | null>(null);
  const [discoverError, setDiscoverError] = useState('');
  // Pull state: keyed by model name → { pct: 0-100, status, error }
  const [pullState, setPullState] = useState<Record<string, { pct: number; status: string; error?: string }>>({});

  // Benchmark state
  const [benchmarkOpen, setBenchmarkOpen] = useState(false);
  const [benchmarkRunning, setBenchmarkRunning] = useState(false);
  const [benchmarkResult, setBenchmarkResult] = useState<BenchmarkResult | null>(null);
  const [benchmarkError, setBenchmarkError] = useState('');
  const [benchmarkModelA, setBenchmarkModelA] = useState('');
  const [benchmarkModelABackend, setBenchmarkModelABackend] = useState<BackendType>('ollama');
  const [benchmarkModelB, setBenchmarkModelB] = useState('');
  const [benchmarkModelBBackend, setBenchmarkModelBBackend] = useState<BackendType>('ollama');
  const [ggufResult, setGgufResult] = useState<{ found: boolean; hf_repo: string | null; gguf_file: string | null; pull_command: string | null; size_gb: number | null } | null>(null);
  const [ggufLoading, setGgufLoading] = useState(false);

  // UI state
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; latency_ms?: number | null; preview?: string | null; error?: string | null } | null>(null);

  // ── load current settings + recommendation ─────────────────────────────────
  function applySettingsToState(s: LLMSettingsResponse) {
    setProvider(s.provider);
    setOllamaUrl(s.ollama_base_url || DEFAULTS.ollama_base_url);
    setOllamaModel(s.ollama_model || DEFAULTS.ollama_model);
    setWxKeyHint(s.watsonx_api_key_hint);
    setWxProjectId(s.watsonx_project_id || '');
    setWxUrl(s.watsonx_url || DEFAULTS.watsonx_url);
    setWxModel(s.watsonx_model || DEFAULTS.watsonx_model);
    setOaiKeyHint(s.openai_api_key_hint);
    setOaiBaseUrl(s.openai_base_url || DEFAULTS.openai_base_url);
    setOaiModel(s.openai_model || DEFAULTS.openai_model);
    setAntKeyHint(s.anthropic_api_key_hint);
    setAntModel(s.anthropic_model || DEFAULTS.anthropic_model);
    setDmrBaseUrl(s.dmr_base_url || 'http://host.docker.internal:9545');
    setDmrModel(s.dmr_model || '');
    setPreviousModel(s.previous_model);
  }

  useEffect(() => {
    const timeout = new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error('timeout')), 4000)
    );
    Promise.race([
      Promise.all([
        api.settings.get(),
        api.settings.getRecommendation(),
      ]),
      timeout,
    ]).then(([s, rec]) => {
      applySettingsToState(s);
      setRecommendation(rec.recommendation);
      setLoaded(true);
      // Fire local advisor when Ollama is the active provider
      if (s.provider === 'ollama') {
        loadAdvisor(false);
      }
    }).catch(() => setLoaded(true));
  }, []);

  async function loadAdvisor(refresh: boolean) {
    setAdvisorLoading(true);
    setAdvisorError('');
    try {
      const data = await api.settings.getLocalAdvisor(refresh);
      setAdvisor(data);
      // Pre-fill benchmark selectors when advisor loads
      if (data.installed_models.length >= 1) {
        setBenchmarkModelA(data.current_model || data.installed_models[0].name);
      }
      if (data.installed_models.length >= 2) {
        const second = data.installed_models.find(m => m.name !== (data.current_model || data.installed_models[0].name));
        if (second) setBenchmarkModelB(second.name);
      }
    } catch {
      setAdvisorError('Could not reach Ollama — make sure it is running locally.');
    } finally {
      setAdvisorLoading(false);
    }
  }

  async function runBenchmark() {
    if (!benchmarkModelA || !benchmarkModelB) return;
    setBenchmarkRunning(true);
    setBenchmarkError('');
    setBenchmarkResult(null);
    try {
      const result = await api.settings.benchmarkModels({
        model_a: benchmarkModelA,
        model_a_backend: benchmarkModelABackend,
        model_b: benchmarkModelB,
        model_b_backend: benchmarkModelBBackend,
      });
      setBenchmarkResult(result);
    } catch (e: unknown) {
      setBenchmarkError(e instanceof Error ? e.message : 'Benchmark failed');
    } finally {
      setBenchmarkRunning(false);
    }
  }

  async function lookupGguf(modelName: string) {
    if (!modelName.trim()) return;
    setGgufLoading(true);
    setGgufResult(null);
    try {
      const r = await api.settings.resolveGguf(modelName.trim());
      setGgufResult(r);
    } catch {
      setGgufResult({ found: false, hf_repo: null, gguf_file: null, pull_command: null, size_gb: null });
    } finally {
      setGgufLoading(false);
    }
  }

  async function runDiscovery(refresh: boolean) {
    setDiscoverLoading(true);
    setDiscoverError('');
    try {
      const data = await api.settings.discoverModels(refresh);
      setDiscoverResult(data);
    } catch {
      setDiscoverError('Could not reach the discovery endpoint.');
    } finally {
      setDiscoverLoading(false);
    }
  }

  async function pullOllamaModel(modelName: string) {
    setPullState(prev => ({ ...prev, [modelName]: { pct: 0, status: 'Starting…' } }));
    try {
      const body = await api.settings.pullModelFetch(modelName);
      if (!body) throw new Error('No response body');
      const reader = body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() ?? '';
        for (const line of lines) {
          const trimmed = line.replace(/^data:\s*/, '').trim();
          if (!trimmed) continue;
          try {
            const evt = JSON.parse(trimmed);
            const total = evt.total ?? 0;
            const completed = evt.completed ?? 0;
            const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
            if (evt.status === 'success') {
              setPullState(prev => ({ ...prev, [modelName]: { pct: 100, status: 'success' } }));
              // Refresh advisor + discovery to show the newly installed model
              await loadAdvisor(true);
              await runDiscovery(true);
              return;
            }
            if (evt.error || evt.status === 'error') {
              setPullState(prev => ({ ...prev, [modelName]: { pct: 0, status: 'error', error: evt.error || 'Pull failed' } }));
              return;
            }
            const label = evt.digest
              ? `${evt.status} — ${pct}%`
              : evt.status;
            setPullState(prev => ({ ...prev, [modelName]: { pct, status: label } }));
          } catch { /* skip malformed line */ }
        }
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Pull failed';
      setPullState(prev => ({ ...prev, [modelName]: { pct: 0, status: 'error', error: msg } }));
    }
  }

  // ── recommendation handlers ────────────────────────────────────────────────
  async function handleApplyRecommendation() {
    setRecLoading(true);
    try {
      const s = await api.settings.applyRecommendation();
      applySettingsToState(s);
      // Re-check recommendation after applying (should now return null)
      const rec = await api.settings.getRecommendation();
      setRecommendation(rec.recommendation);
    } catch { /* ignore */ } finally {
      setRecLoading(false);
    }
  }

  async function handleRollback() {
    setRecLoading(true);
    try {
      const s = await api.settings.rollbackModel();
      applySettingsToState(s);
      const rec = await api.settings.getRecommendation();
      setRecommendation(rec.recommendation);
    } catch { /* ignore */ } finally {
      setRecLoading(false);
    }
  }

  async function handleSnooze() {
    setRecLoading(true);
    try {
      await api.settings.snoozeRecommendation();
      setRecommendation(null);
    } catch { /* ignore */ } finally {
      setRecLoading(false);
    }
  }

  // ── build payload ──────────────────────────────────────────────────────────
  function buildPayload(): LLMSettingsSave {
    const p: LLMSettingsSave = { provider };
    p.ollama_base_url = ollamaUrl || null;
    p.ollama_model = ollamaModel || null;
    if (wxKey) p.watsonx_api_key = wxKey;
    p.watsonx_project_id = wxProjectId || null;
    p.watsonx_url = wxUrl || null;
    p.watsonx_model = wxModel || null;
    if (oaiKey) p.openai_api_key = oaiKey;
    p.openai_base_url = oaiBaseUrl || null;
    p.openai_model = oaiModel || null;
    if (antKey) p.anthropic_api_key = antKey;
    p.anthropic_model = antModel || null;
    // Docker Model Runner
    p.dmr_base_url = dmrBaseUrl || null;
    p.dmr_model = dmrModel || null;
    return p;
  }

  // ── save ───────────────────────────────────────────────────────────────────
  async function handleSave() {
    setSaving(true);
    setSaveError('');
    setSaveSuccess(false);
    setTestResult(null);
    try {
      const s = await api.settings.save(buildPayload());
      applySettingsToState(s);
      // clear plaintext key fields after save
      setWxKey(''); setOaiKey(''); setAntKey('');
      setSaveSuccess(true);
      // Refresh recommendation after provider/model change
      const rec = await api.settings.getRecommendation();
      setRecommendation(rec.recommendation);
    } catch (e: any) {
      setSaveError(e?.message || 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  }

  // ── test connection ────────────────────────────────────────────────────────
  async function handleTest() {
    setTesting(true);
    setTestResult(null);
    setSaveSuccess(false);
    try {
      const result = await api.settings.test(buildPayload());
      setTestResult(result);
    } catch (e: any) {
      setTestResult({ ok: false, error: e?.message || 'Test request failed' });
    } finally {
      setTesting(false);
    }
  }

  if (!loaded) {
    return (
      <div className="page-body" style={{ paddingTop: '3rem' }}>
        <InlineLoading description="Loading settings…" />
      </div>
    );
  }

  // ── table style helpers (used in benchmark scorecard) ──────────────────────
  const thStyle: React.CSSProperties = {
    padding: '0.35rem 0.5rem', textAlign: 'left', fontWeight: 600,
    fontSize: '0.75rem', borderBottom: '1px solid #d0e2ff',
  };
  const tdStyle: React.CSSProperties = {
    padding: '0.3rem 0.5rem', borderBottom: '1px solid #e8ecff',
    fontSize: '0.8125rem', color: '#161616',
  };

  return (
    <>
      <div className="page-header-band">
        <div className="page-header-inner" style={{ display: 'flex', alignItems: 'flex-end', gap: '0.75rem' }}>
          <SettingsIcon size={24} style={{ marginBottom: '0.2rem', color: '#525252' }} />
          <div>
            <h1 className="page-heading">LLM Provider Settings</h1>
            <p className="page-description">
              Choose and configure the AI model used to normalize server inventory data.
            </p>
          </div>
        </div>
      </div>

      <div className="page-body" style={{ maxWidth: 680 }}>

        {/* ── Model recommendation banner ──────────────────────────── */}
        {recommendation && (
          <div style={{ marginBottom: '1.5rem', padding: '1rem', background: '#edf4ff', border: '1px solid #a6c8ff', borderLeft: '4px solid #0f62fe' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem' }}>
              <div style={{ flex: 1 }}>
                <p style={{ fontWeight: 600, color: '#161616', marginBottom: '0.25rem', fontSize: '0.875rem' }}>
                  Model update available
                  <Tag type="blue" size="sm" style={{ marginLeft: '0.5rem', verticalAlign: 'middle' }}>Recommended</Tag>
                </p>
                <p style={{ color: '#393939', fontSize: '0.8125rem', marginBottom: '0.5rem' }}>
                  <strong>{recommendation.recommended_label}</strong> ({recommendation.recommended_model})
                </p>
                <p style={{ color: '#525252', fontSize: '0.8125rem', lineHeight: 1.5 }}>{recommendation.reason}</p>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', flexShrink: 0, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                {recLoading ? (
                  <InlineLoading description="Updating…" style={{ flex: 'none' }} />
                ) : (
                  <>
                    <Button kind="primary" size="sm" onClick={handleApplyRecommendation}>
                      Use recommended
                    </Button>
                    {previousModel && (
                      <Button kind="secondary" size="sm" onClick={handleRollback}>
                        Rollback to {previousModel.split('/').pop()}
                      </Button>
                    )}
                    <Button kind="ghost" size="sm" onClick={handleSnooze}>
                      Dismiss for 7 days
                    </Button>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Rollback available even when no current recommendation */}
        {!recommendation && previousModel && (
          <div style={{ marginBottom: '1.5rem', padding: '0.75rem 1rem', background: '#f4f4f4', border: '1px solid #e0e0e0', display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <p style={{ flex: 1, fontSize: '0.8125rem', color: '#525252', margin: 0 }}>
              Previously updated from <strong>{previousModel.split('/').pop()}</strong>.
            </p>
            {recLoading ? (
              <InlineLoading description="Reverting…" style={{ flex: 'none' }} />
            ) : (
              <Button kind="ghost" size="sm" onClick={handleRollback}>
                Rollback
              </Button>
            )}
          </div>
        )}

        {/* ── Provider picker ─────────────────────────────────────── */}
        <section style={{ marginBottom: '2rem' }}>
          <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '1rem', color: '#161616' }}>
            Active provider
          </h2>
          <RadioButtonGroup
            legendText=""
            name="llm-provider"
            valueSelected={provider}
            onChange={(val) => { setProvider(val as LLMProvider); setTestResult(null); setSaveSuccess(false); }}
            orientation="vertical"
          >
            <RadioButton labelText="Ollama (local — no API key required)" value="ollama" id="prov-ollama" />
            <RadioButton
              labelText={
                <span>
                  IBM watsonx.ai&nbsp;
                  <Tag type="blue" size="sm" style={{ verticalAlign: 'middle' }}>Recommended</Tag>
                </span>
              }
              value="watsonx"
              id="prov-watsonx"
            />
            <RadioButton labelText="OpenAI-compatible (OpenAI, Azure OpenAI, vLLM)" value="openai" id="prov-openai" />
            <RadioButton labelText="Anthropic (Claude)" value="anthropic" id="prov-anthropic" />
            <RadioButton labelText="Docker Model Runner (local — Docker Desktop ≥ 4.25)" value="docker_model_runner" id="prov-dmr" />
          </RadioButtonGroup>
        </section>

        <div style={{ borderTop: '1px solid #e5e7eb', marginBottom: '2rem' }} />

        {/* ── Ollama fields ────────────────────────────────────────── */}
        {provider === 'ollama' && (
          <section style={{ marginBottom: '1.5rem' }}>
            <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '1rem', color: '#161616' }}>
              Ollama configuration
            </h2>
            <p style={{ color: '#525252', marginBottom: '1.25rem', fontSize: '0.875rem', lineHeight: 1.6 }}>
              Ollama must be running on your local machine with the desired model pulled.
              The containers reach it via <code>host.docker.internal</code>.
              Run: <code>ollama pull phi4-mini</code>
            </p>
            <TextInput
              id="ollama-url"
              labelText="Ollama base URL"
              value={ollamaUrl}
              onChange={e => setOllamaUrl(e.target.value)}
              placeholder={DEFAULTS.ollama_base_url}
              style={{ marginBottom: '1rem' }}
            />
            <TextInput
              id="ollama-model"
              labelText="Model name"
              value={ollamaModel}
              onChange={e => setOllamaModel(e.target.value)}
              placeholder={DEFAULTS.ollama_model}
              helperText="Any model pulled in Ollama (e.g. phi4-mini, llama3.2, mistral)"
            />
          </section>
        )}

        {/* ── Docker Model Runner fields ───────────────────────────── */}
        {provider === 'docker_model_runner' && (
          <section style={{ marginBottom: '1.5rem' }}>
            <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.5rem', color: '#161616' }}>
              Docker Model Runner configuration
            </h2>
            <p style={{ color: '#525252', marginBottom: '1.25rem', fontSize: '0.875rem', lineHeight: 1.6 }}>
              Requires Docker Desktop ≥ 4.25 with Model Runner enabled.
              Pull a model first: <code>docker model pull ai/phi4-mini</code>
              {' or '}
              <code>docker model pull hf.co/&lt;org&gt;/&lt;model&gt;-GGUF</code>.
              The endpoint is OpenAI-compatible — no API key required.
            </p>
            <TextInput
              id="dmr-url"
              labelText="Docker Model Runner URL"
              value={dmrBaseUrl}
              onChange={e => setDmrBaseUrl(e.target.value)}
              placeholder="http://host.docker.internal:9545"
              style={{ marginBottom: '1rem' }}
            />
            <TextInput
              id="dmr-model"
              labelText="Model name"
              value={dmrModel}
              onChange={e => setDmrModel(e.target.value)}
              placeholder="ai/phi4-mini or hf.co/microsoft/Phi-4-mini-instruct-GGUF"
              helperText="Enter the model name exactly as shown in 'docker model list'"
            />
          </section>
        )}

        {/* ── Local AI Advisor card ─────────────────────────────────── */}
        {provider === 'ollama' && (
          <section style={{ marginBottom: '1.5rem', border: '1px solid #d0e2ff', borderRadius: 4, background: '#f0f4ff', padding: '1rem 1.25rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem' }}>
              <h2 style={{ fontSize: '0.9375rem', fontWeight: 600, color: '#0043ce', margin: 0 }}>
                Local AI Advisor
              </h2>
              <button
                onClick={() => loadAdvisor(true)}
                disabled={advisorLoading}
                style={{ fontSize: '0.8125rem', color: '#0043ce', background: 'none', border: 'none', cursor: 'pointer', padding: 0, textDecoration: 'underline' }}
              >
                ↻ Refresh
              </button>
            </div>

            {advisorLoading && <InlineLoading description="Checking Ollama…" />}

            {advisorError && !advisorLoading && (
              <p style={{ fontSize: '0.8125rem', color: '#da1e28', margin: 0 }}>{advisorError}</p>
            )}

            {advisor && !advisorLoading && (
              <>
                {/* Hardware summary */}
                <p style={{ fontSize: '0.8125rem', color: '#161616', margin: '0 0 0.75rem', lineHeight: 1.6 }}>
                  <strong>CPU:</strong> {advisor.cpu_model} ({advisor.cpu_arch})
                  {' · '}<strong>RAM:</strong> {advisor.ram_gb} GB
                  {' · '}<strong>Ollama:</strong>{' '}
                  {advisor.ollama_reachable
                    ? <span style={{ color: '#198038' }}>reachable</span>
                    : <span style={{ color: '#da1e28' }}>unreachable — is Ollama running?</span>}
                </p>

                {/* Installed models list */}
                {advisor.installed_models.length === 0 ? (
                  <p style={{ fontSize: '0.8125rem', color: '#525252', margin: '0 0 0.5rem' }}>
                    No models installed. Run <code>ollama pull phi4-mini</code> to get started.
                  </p>
                ) : (
                  <div style={{ marginBottom: '0.75rem' }}>
                    <p style={{ fontSize: '0.75rem', fontWeight: 600, color: '#525252', margin: '0 0 0.35rem' }}>INSTALLED MODELS</p>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                      {advisor.installed_models.map(m => (
                        <div key={m.name} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8125rem' }}>
                          <code style={{ color: m.recommended ? '#0043ce' : '#161616', fontWeight: m.recommended ? 700 : 400 }}>{m.name}</code>
                          <span style={{ color: '#6f6f6f' }}>{m.size_gb} GB</span>
                          {m.recommended && <span style={{ background: '#0043ce', color: '#fff', fontSize: '0.6875rem', padding: '0.1rem 0.4rem', borderRadius: 3 }}>BEST FIT</span>}
                          {!m.fits_in_ram && <span style={{ color: '#da1e28', fontSize: '0.75rem' }}>⚠ may not fit in RAM</span>}
                          {advisor.current_model && m.name.startsWith(advisor.current_model.split(':')[0]) && m.name === advisor.current_model && (
                            <span style={{ color: '#6f6f6f', fontSize: '0.75rem' }}>← active</span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Pull suggestion */}
                {advisor.pull_suggestion && (
                  <div style={{ background: '#fff', border: '1px solid #d0e2ff', borderRadius: 4, padding: '0.625rem 0.875rem', marginTop: '0.5rem' }}>
                    <p style={{ fontSize: '0.8125rem', margin: 0, color: '#0043ce' }}>
                      <strong>Suggestion:</strong> Pull <code>{advisor.pull_suggestion.model}</code> ({advisor.pull_suggestion.label}) for better structured-JSON extraction accuracy.
                    </p>
                    <code style={{ fontSize: '0.8125rem', color: '#161616', display: 'block', marginTop: '0.25rem' }}>
                      ollama pull {advisor.pull_suggestion.model}
                    </code>
                  </div>
                )}

                {/* ── Compare Models toggle ─────────────────────────── */}
                {advisor.installed_models.length >= 1 && (
                  <div style={{ marginTop: '1rem', borderTop: '1px solid #d0e2ff', paddingTop: '0.75rem' }}>
                    <button
                      id="advisor-benchmark-toggle"
                      onClick={() => { setBenchmarkOpen(o => !o); setBenchmarkResult(null); setBenchmarkError(''); }}
                      style={{ fontSize: '0.8125rem', color: '#0043ce', background: 'none', border: 'none', cursor: 'pointer', padding: 0, textDecoration: 'underline' }}
                    >
                      {benchmarkOpen ? '▲ Hide Compare Models' : '▼ Compare Models'}
                    </button>

                    {benchmarkOpen && (
                      <div style={{ marginTop: '0.75rem' }}>
                        <p style={{ fontSize: '0.75rem', color: '#525252', margin: '0 0 0.75rem' }}>
                          Runs 8 synthetic server records through both models and scores accuracy + speed equally.
                          <br />
                          <strong>Score = 50% accuracy + 50% speed</strong> (speed ceiling: 30 s/record → score 0).
                          Expect 1–3 min total run time.
                        </p>

                        {/* Model selectors */}
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '0.75rem' }}>
                          <div>
                            <label style={{ fontSize: '0.75rem', fontWeight: 600, display: 'block', marginBottom: '0.25rem', color: '#161616' }}>
                              Model A
                            </label>
                            <Select
                              id="bm-model-a"
                              labelText=""
                              hideLabel
                              value={benchmarkModelA}
                              onChange={e => setBenchmarkModelA(e.target.value)}
                              size="sm"
                            >
                              {advisor.installed_models.map(m => (
                                <SelectItem key={m.name} value={m.name} text={m.name} />
                              ))}
                            </Select>
                            <Select
                              id="bm-backend-a"
                              labelText="Backend"
                              value={benchmarkModelABackend}
                              onChange={e => setBenchmarkModelABackend(e.target.value as BackendType)}
                              size="sm"
                              style={{ marginTop: '0.35rem' }}
                            >
                              <SelectItem value="ollama" text="Ollama" />
                              <SelectItem value="docker_model_runner" text="Docker Model Runner" />
                            </Select>
                          </div>
                          <div>
                            <label style={{ fontSize: '0.75rem', fontWeight: 600, display: 'block', marginBottom: '0.25rem', color: '#161616' }}>
                              Model B
                            </label>
                            <Select
                              id="bm-model-b"
                              labelText=""
                              hideLabel
                              value={benchmarkModelB}
                              onChange={e => setBenchmarkModelB(e.target.value)}
                              size="sm"
                            >
                              <SelectItem value="" text="— select model —" />
                              {advisor.installed_models.map(m => (
                                <SelectItem key={m.name} value={m.name} text={m.name} />
                              ))}
                            </Select>
                            <Select
                              id="bm-backend-b"
                              labelText="Backend"
                              value={benchmarkModelBBackend}
                              onChange={e => { setBenchmarkModelBBackend(e.target.value as BackendType); setGgufResult(null); }}
                              size="sm"
                              style={{ marginTop: '0.35rem' }}
                            >
                              <SelectItem value="ollama" text="Ollama" />
                              <SelectItem value="docker_model_runner" text="Docker Model Runner" />
                            </Select>

                            {/* Find on HuggingFace — shown when DMR backend selected */}
                            {benchmarkModelBBackend === 'docker_model_runner' && (
                              <div style={{ marginTop: '0.5rem' }}>
                                <button
                                  onClick={() => lookupGguf(benchmarkModelB || benchmarkModelA)}
                                  disabled={ggufLoading}
                                  style={{ fontSize: '0.8125rem', color: '#0043ce', background: 'none', border: 'none', cursor: 'pointer', padding: 0, textDecoration: 'underline' }}
                                >
                                  {ggufLoading ? 'Looking up…' : '🔍 Find on HuggingFace'}
                                </button>
                                {ggufResult && (
                                  <div style={{ marginTop: '0.4rem', fontSize: '0.75rem', background: '#fff', border: '1px solid #d0e2ff', borderRadius: 3, padding: '0.4rem 0.6rem' }}>
                                    {ggufResult.found ? (
                                      <>
                                        <div style={{ color: '#198038', fontWeight: 600, marginBottom: '0.2rem' }}>Found: {ggufResult.hf_repo}</div>
                                        {ggufResult.size_gb && <div style={{ color: '#525252' }}>Size: ~{ggufResult.size_gb} GB ({ggufResult.gguf_file})</div>}
                                        <div style={{ marginTop: '0.3rem' }}>
                                          <code style={{ userSelect: 'all', color: '#161616', fontSize: '0.75rem' }}>{ggufResult.pull_command}</code>
                                        </div>
                                      </>
                                    ) : (
                                      <span style={{ color: '#da1e28' }}>No GGUF found on HuggingFace Hub for this model name.</span>
                                    )}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        </div>

                        <Button
                          kind="primary"
                          size="sm"
                          onClick={runBenchmark}
                          disabled={benchmarkRunning || !benchmarkModelA || !benchmarkModelB}
                        >
                          {benchmarkRunning ? 'Running…' : 'Run Benchmark'}
                        </Button>

                        {benchmarkRunning && (
                          <div style={{ marginTop: '0.75rem' }}>
                            <InlineLoading description="Benchmarking both models — this may take 1–3 minutes…" />
                          </div>
                        )}

                        {benchmarkError && !benchmarkRunning && (
                          <InlineNotification
                            kind="error"
                            title="Benchmark failed"
                            subtitle={benchmarkError}
                            lowContrast
                            style={{ marginTop: '0.75rem' }}
                          />
                        )}

                        {/* ── Scorecard ─────────────────────────────── */}
                        {benchmarkResult && !benchmarkRunning && (() => {
                          const a = benchmarkResult.model_a;
                          const b = benchmarkResult.model_b;
                          const winnerLabel =
                            benchmarkResult.winner === 'model_a' ? a.name
                            : benchmarkResult.winner === 'model_b' ? b.name
                            : 'Tie';
                          const winnerKind = benchmarkResult.winner === 'tie' ? 'gray' : 'green';

                          return (
                            <div style={{ marginTop: '1rem' }}>
                              {/* Winner badge + recommendation */}
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
                                <Tag type={winnerKind} size="md">
                                  {benchmarkResult.winner === 'tie' ? 'Tie' : `Winner: ${winnerLabel}`}
                                </Tag>
                              </div>
                              <InlineNotification
                                kind="info"
                                title=""
                                subtitle={benchmarkResult.recommendation}
                                lowContrast
                                style={{ marginBottom: '0.75rem' }}
                              />

                              {/* Summary table */}
                              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
                                <thead>
                                  <tr style={{ background: '#e0e8ff' }}>
                                    <th style={thStyle}>Metric</th>
                                    <th style={thStyle}>{a.name}{a.backend !== 'ollama' ? ` (${a.backend})` : ''}</th>
                                    <th style={thStyle}>{b.name}{b.backend !== 'ollama' ? ` (${b.backend})` : ''}</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  <tr style={{ background: '#f0f4ff' }}>
                                    <td style={tdStyle}><strong>Composite score</strong></td>
                                    <td style={{ ...tdStyle, fontWeight: 700, color: benchmarkResult.winner === 'model_a' ? '#198038' : '#161616' }}>{a.composite_score}</td>
                                    <td style={{ ...tdStyle, fontWeight: 700, color: benchmarkResult.winner === 'model_b' ? '#198038' : '#161616' }}>{b.composite_score}</td>
                                  </tr>
                                  <tr>
                                    <td style={tdStyle}>Accuracy</td>
                                    <td style={tdStyle}>{a.accuracy_pct.toFixed(1)}%</td>
                                    <td style={tdStyle}>{b.accuracy_pct.toFixed(1)}%</td>
                                  </tr>
                                  <tr>
                                    <td style={tdStyle}>Speed score</td>
                                    <td style={tdStyle}>{a.speed_score.toFixed(1)}</td>
                                    <td style={tdStyle}>{b.speed_score.toFixed(1)}</td>
                                  </tr>
                                  <tr>
                                    <td style={tdStyle}>Avg latency</td>
                                    <td style={tdStyle}>{(a.avg_latency_ms / 1000).toFixed(1)} s</td>
                                    <td style={tdStyle}>{(b.avg_latency_ms / 1000).toFixed(1)} s</td>
                                  </tr>
                                  <tr>
                                    <td style={tdStyle}>Reachable</td>
                                    <td style={tdStyle}>{a.reachable ? '✓' : '✗'}</td>
                                    <td style={tdStyle}>{b.reachable ? '✓' : '✗'}</td>
                                  </tr>
                                </tbody>
                              </table>

                              {/* Per-case detail */}
                              <details style={{ marginTop: '0.75rem' }}>
                                <summary style={{ fontSize: '0.8125rem', cursor: 'pointer', color: '#0043ce' }}>
                                  Per-case detail ({a.cases.length} cases)
                                </summary>
                                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.75rem', marginTop: '0.5rem' }}>
                                  <thead>
                                    <tr style={{ background: '#e0e8ff' }}>
                                      <th style={thStyle}>#</th>
                                      <th style={thStyle}>Case</th>
                                      <th style={thStyle}>{a.name} passed/total</th>
                                      <th style={thStyle}>{a.name} latency</th>
                                      <th style={thStyle}>{b.name} passed/total</th>
                                      <th style={thStyle}>{b.name} latency</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {a.cases.map((ac, i) => {
                                      const bc = b.cases[i];
                                      return (
                                        <tr key={ac.case_id} style={{ background: i % 2 === 0 ? '#f9fbff' : '#fff' }}>
                                          <td style={tdStyle}>{ac.case_id}</td>
                                          <td style={{ ...tdStyle, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={ac.description}>{ac.description}</td>
                                          <td style={{ ...tdStyle, color: ac.passed === ac.total ? '#198038' : '#da1e28' }}>{ac.passed}/{ac.total}</td>
                                          <td style={tdStyle}>{(ac.latency_ms / 1000).toFixed(1)} s</td>
                                          <td style={{ ...tdStyle, color: bc?.passed === bc?.total ? '#198038' : '#da1e28' }}>{bc?.passed ?? '—'}/{bc?.total ?? '—'}</td>
                                          <td style={tdStyle}>{bc ? `${(bc.latency_ms / 1000).toFixed(1)} s` : '—'}</td>
                                        </tr>
                                      );
                                    })}
                                  </tbody>
                                </table>
                              </details>
                            </div>
                          );
                        })()}
                      </div>
                    )}
                  </div>
                )}

                {/* ── Discover Models section ───────────────────────── */}
                <div style={{ marginTop: '1rem', borderTop: '1px solid #d0e2ff', paddingTop: '0.75rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
                    <button
                      onClick={() => {
                        const opening = !discoverOpen;
                        setDiscoverOpen(opening);
                        if (opening && !discoverResult) runDiscovery(false);
                      }}
                      style={{ fontSize: '0.8125rem', color: '#0043ce', background: 'none', border: 'none', cursor: 'pointer', padding: 0, textDecoration: 'underline' }}
                    >
                      {discoverOpen ? '▲ Hide Discover Models' : '🔭 Check for New Models'}
                    </button>
                    {discoverOpen && discoverResult && (
                      <button
                        onClick={() => runDiscovery(true)}
                        disabled={discoverLoading}
                        style={{ fontSize: '0.75rem', color: '#0043ce', background: 'none', border: 'none', cursor: 'pointer', padding: 0, textDecoration: 'underline' }}
                      >
                        ↻ Refresh
                      </button>
                    )}
                  </div>

                  {discoverOpen && (
                    <div style={{ marginTop: '0.75rem' }}>
                      {discoverLoading && <InlineLoading description="Querying model registries…" />}

                      {discoverError && !discoverLoading && (
                        <p style={{ fontSize: '0.8125rem', color: '#da1e28', margin: 0 }}>{discoverError}</p>
                      )}

                      {discoverResult && !discoverLoading && (
                        <>
                          {/* Registry reachability notice */}
                          {!discoverResult.sources_reachable['ollama'] && (
                            <p style={{ fontSize: '0.75rem', color: '#525252', margin: '0 0 0.5rem', background: '#f4f4f4', border: '1px solid #e0e0e0', borderRadius: 3, padding: '0.35rem 0.6rem' }}>
                              Ollama.com unreachable from container — showing curated catalog. Results are still accurate; live registry data would include newest community models.
                            </p>
                          )}

                          {/* ── Currently installed reference row ── */}
                          {discoverResult.current_model && (
                            <div style={{ marginBottom: '0.5rem' }}>
                              <p style={{ fontSize: '0.75rem', fontWeight: 600, color: '#525252', margin: '0 0 0.3rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Currently installed</p>
                              <div style={{ background: '#f0f4ff', border: '2px solid #0043ce', borderRadius: 4, padding: '0.5rem 0.75rem', display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                                <code style={{ fontSize: '0.875rem', fontWeight: 700, color: '#0043ce' }}>{discoverResult.current_model}</code>
                                <span style={{ fontSize: '0.75rem', background: '#0043ce', color: '#fff', padding: '0.1rem 0.4rem', borderRadius: 3 }}>ACTIVE</span>
                                {discoverResult.current_task_fit !== null && (
                                  <span style={{ fontSize: '0.75rem', color: '#525252' }}>
                                    task-fit: <strong style={{ color: discoverResult.current_task_fit >= 8 ? '#198038' : discoverResult.current_task_fit >= 6 ? '#916a00' : '#da1e28' }}>{discoverResult.current_task_fit}</strong>/10
                                  </span>
                                )}
                                <span style={{ fontSize: '0.75rem', color: '#525252', marginLeft: 'auto' }}>benchmark baseline</span>
                              </div>
                            </div>
                          )}

                          {discoverResult.discovered.length === 0 ? (
                            <p style={{ fontSize: '0.8125rem', color: '#525252', margin: 0 }}>
                              All known candidates are already installed.
                            </p>
                          ) : (
                            <>
                              <p style={{ fontSize: '0.75rem', color: '#525252', margin: '0 0 0.4rem' }}>
                                Candidates ranked by task-fit score — {discoverResult.ram_gb} GB RAM available.
                                {discoverResult.current_task_fit !== null && ` Models scoring above ${discoverResult.current_task_fit} improve on your current setup.`}
                              </p>
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                                {discoverResult.discovered.map((m: DiscoveredModel) => {
                                  const ps = pullState[m.name];
                                  const isPulling = ps && ps.status !== 'success' && ps.status !== 'error';
                                  const isPulled = ps?.status === 'success';
                                  const pullError = ps?.status === 'error' ? ps.error : undefined;
                                  const betterThanCurrent = discoverResult.current_task_fit !== null && m.task_fit > discoverResult.current_task_fit;
                                  const sameCurrent = discoverResult.current_task_fit !== null && m.task_fit === discoverResult.current_task_fit;

                                  return (
                                    <div key={m.name} style={{
                                      background: '#fff',
                                      border: `1px solid ${betterThanCurrent ? '#a7f3d0' : m.fits_in_ram ? '#d0e2ff' : '#ffd2d2'}`,
                                      borderRadius: 4,
                                      padding: '0.6rem 0.75rem',
                                      opacity: m.fits_in_ram ? 1 : 0.7,
                                    }}>
                                      {/* ── header row ── */}
                                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.3rem' }}>
                                        <code style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#161616' }}>{m.name}</code>
                                        <span style={{ fontSize: '0.6875rem', background: m.source === 'ollama' ? '#e0e8ff' : '#e8f5e9', color: m.source === 'ollama' ? '#0043ce' : '#198038', padding: '0.1rem 0.35rem', borderRadius: 3, fontWeight: 600 }}>
                                          {m.source}
                                        </span>
                                        {m.size_gb > 0 && <span style={{ fontSize: '0.75rem', color: '#6f6f6f' }}>{m.size_gb} GB</span>}
                                        {!m.fits_in_ram && <span style={{ fontSize: '0.75rem', color: '#da1e28' }}>⚠ may exceed RAM</span>}
                                        {/* task-fit bar */}
                                        <span style={{ fontSize: '0.75rem', color: '#525252', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                                          task-fit:&nbsp;
                                          <strong style={{ color: m.task_fit >= 9 ? '#198038' : m.task_fit >= 7 ? '#0043ce' : m.task_fit >= 5 ? '#525252' : '#da1e28' }}>
                                            {m.task_fit}
                                          </strong>/10
                                          {betterThanCurrent && <span style={{ background: '#d1fae5', color: '#065f46', fontSize: '0.6875rem', padding: '0 0.3rem', borderRadius: 3, fontWeight: 600 }}>▲ better</span>}
                                          {sameCurrent && <span style={{ background: '#fef3c7', color: '#92400e', fontSize: '0.6875rem', padding: '0 0.3rem', borderRadius: 3 }}>= same</span>}
                                        </span>
                                        {m.pull_count > 0 && <span style={{ fontSize: '0.75rem', color: '#6f6f6f', marginLeft: 'auto' }}>{(m.pull_count / 1_000_000).toFixed(1)}M pulls</span>}
                                      </div>

                                      {/* description */}
                                      {m.description && (
                                        <p style={{ fontSize: '0.75rem', color: '#525252', margin: '0 0 0.35rem', lineHeight: 1.4 }}>{m.description}</p>
                                      )}

                                      {/* pull command + action row */}
                                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                                        <code style={{ fontSize: '0.75rem', color: '#161616', userSelect: 'all', flexGrow: 1 }}>{m.pull_command}</code>

                                        {/* Pull button — only for ollama source models */}
                                        {m.source === 'ollama' && !isPulled && (
                                          <button
                                            onClick={() => pullOllamaModel(m.name)}
                                            disabled={isPulling}
                                            style={{
                                              fontSize: '0.75rem', padding: '0.25rem 0.6rem',
                                              background: isPulling ? '#e0e8ff' : '#0043ce', color: '#fff',
                                              border: 'none', borderRadius: 3, cursor: isPulling ? 'default' : 'pointer',
                                              whiteSpace: 'nowrap', flexShrink: 0,
                                            }}
                                          >
                                            {isPulling ? `↓ ${ps.pct}%` : '↓ Pull'}
                                          </button>
                                        )}
                                        {isPulled && <span style={{ fontSize: '0.75rem', color: '#198038', fontWeight: 600, flexShrink: 0 }}>✓ Installed</span>}

                                        {/* Benchmark vs current shortcut */}
                                        {discoverResult.current_model && (
                                          <button
                                            onClick={() => {
                                              setBenchmarkModelA(discoverResult.current_model!);
                                              setBenchmarkModelABackend('ollama');
                                              setBenchmarkModelB(m.name);
                                              setBenchmarkModelBBackend('ollama');
                                              setBenchmarkOpen(true);
                                              setBenchmarkResult(null);
                                              setBenchmarkError('');
                                              // Scroll up to the benchmark section
                                              setTimeout(() => {
                                                document.getElementById('advisor-benchmark-toggle')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                              }, 100);
                                            }}
                                            style={{
                                              fontSize: '0.75rem', padding: '0.25rem 0.6rem',
                                              background: 'none', color: '#0043ce',
                                              border: '1px solid #0043ce', borderRadius: 3,
                                              cursor: 'pointer', whiteSpace: 'nowrap', flexShrink: 0,
                                            }}
                                          >
                                            ⚖ Benchmark vs {discoverResult.current_model}
                                          </button>
                                        )}
                                      </div>

                                      {/* pull progress bar */}
                                      {isPulling && ps.pct > 0 && (
                                        <div style={{ marginTop: '0.35rem', height: 4, background: '#e0e8ff', borderRadius: 2 }}>
                                          <div style={{ height: '100%', width: `${ps.pct}%`, background: '#0043ce', borderRadius: 2, transition: 'width 0.3s' }} />
                                        </div>
                                      )}
                                      {isPulling && ps.status && (
                                        <p style={{ fontSize: '0.7rem', color: '#525252', margin: '0.2rem 0 0' }}>{ps.status}</p>
                                      )}
                                      {pullError && (
                                        <p style={{ fontSize: '0.75rem', color: '#da1e28', margin: '0.25rem 0 0' }}>Pull failed: {pullError}</p>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            </>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </div>

              </>
            )}
          </section>
        )}

        {/* ── watsonx.ai fields ────────────────────────────────────── */}
        {provider === 'watsonx' && (
          <section style={{ marginBottom: '1.5rem' }}>
            <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '1rem', color: '#161616' }}>
              IBM watsonx.ai configuration
            </h2>
            <p style={{ color: '#525252', marginBottom: '1.25rem', fontSize: '0.875rem', lineHeight: 1.6 }}>
              Requires an IBM Cloud account with watsonx.ai enabled. Get your API key at{' '}
              <a href="https://cloud.ibm.com/iam/apikeys" target="_blank" rel="noreferrer">
                cloud.ibm.com/iam/apikeys
              </a>{' '}
              and your Project ID from the watsonx.ai project settings page.
            </p>
            <PasswordInput
              id="wx-key"
              labelText={wxKeyHint ? `IBM Cloud API key (saved: ${wxKeyHint})` : 'IBM Cloud API key'}
              value={wxKey}
              onChange={e => setWxKey(e.target.value)}
              placeholder={wxKeyHint ? 'Enter new key to replace saved key' : 'Paste your IBM Cloud API key'}
              style={{ marginBottom: '1rem' }}
            />
            <TextInput
              id="wx-project"
              labelText="watsonx.ai Project ID"
              value={wxProjectId}
              onChange={e => setWxProjectId(e.target.value)}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              helperText="Found in your watsonx.ai project → Manage → General"
              style={{ marginBottom: '1rem' }}
            />
            <TextInput
              id="wx-url"
              labelText="Region endpoint URL"
              value={wxUrl}
              onChange={e => setWxUrl(e.target.value)}
              placeholder={DEFAULTS.watsonx_url}
              helperText="us-south, eu-de, eu-gb, jp-tok, au-syd — see IBM Cloud docs"
              style={{ marginBottom: '1rem' }}
            />
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 400, color: '#525252', marginBottom: '0.5rem' }}>
                Model ID
              </label>
              <select
                value={wxModel}
                onChange={e => setWxModel(e.target.value)}
                style={{ width: '100%', padding: '0.6875rem 1rem', border: '1px solid #8d8d8d', background: '#fff', fontSize: '0.875rem', borderRadius: 0, color: '#161616' }}
              >
                {WATSONX_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
              <p style={{ fontSize: '0.75rem', color: '#525252', marginTop: '0.25rem' }}>
                Granite 3 8B is recommended for structured JSON extraction tasks.
              </p>
            </div>
          </section>
        )}

        {/* ── OpenAI fields ────────────────────────────────────────── */}
        {provider === 'openai' && (
          <section style={{ marginBottom: '1.5rem' }}>
            <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '1rem', color: '#161616' }}>
              OpenAI-compatible configuration
            </h2>
            <p style={{ color: '#525252', marginBottom: '1.25rem', fontSize: '0.875rem', lineHeight: 1.6 }}>
              Works with OpenAI, Azure OpenAI, or any endpoint that implements the{' '}
              <code>/v1/chat/completions</code> API (e.g. local vLLM, LM Studio).
            </p>
            <PasswordInput
              id="oai-key"
              labelText={oaiKeyHint ? `API key (saved: ${oaiKeyHint})` : 'API key'}
              value={oaiKey}
              onChange={e => setOaiKey(e.target.value)}
              placeholder={oaiKeyHint ? 'Enter new key to replace saved key' : 'sk-...'}
              style={{ marginBottom: '1rem' }}
            />
            <TextInput
              id="oai-base-url"
              labelText="Base URL"
              value={oaiBaseUrl}
              onChange={e => setOaiBaseUrl(e.target.value)}
              placeholder={DEFAULTS.openai_base_url}
              helperText="For Azure OpenAI: https://<resource>.openai.azure.com"
              style={{ marginBottom: '1rem' }}
            />
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 400, color: '#525252', marginBottom: '0.5rem' }}>
                Model
              </label>
              <select
                value={oaiModel}
                onChange={e => setOaiModel(e.target.value)}
                style={{ width: '100%', padding: '0.6875rem 1rem', border: '1px solid #8d8d8d', background: '#fff', fontSize: '0.875rem', borderRadius: 0, color: '#161616' }}
              >
                {OPENAI_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
          </section>
        )}

        {/* ── Anthropic fields ─────────────────────────────────────── */}
        {provider === 'anthropic' && (
          <section style={{ marginBottom: '1.5rem' }}>
            <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '1rem', color: '#161616' }}>
              Anthropic configuration
            </h2>
            <PasswordInput
              id="ant-key"
              labelText={antKeyHint ? `API key (saved: ${antKeyHint})` : 'API key'}
              value={antKey}
              onChange={e => setAntKey(e.target.value)}
              placeholder={antKeyHint ? 'Enter new key to replace saved key' : 'sk-ant-...'}
              style={{ marginBottom: '1rem' }}
            />
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 400, color: '#525252', marginBottom: '0.5rem' }}>
                Model
              </label>
              <select
                value={antModel}
                onChange={e => setAntModel(e.target.value)}
                style={{ width: '100%', padding: '0.6875rem 1rem', border: '1px solid #8d8d8d', background: '#fff', fontSize: '0.875rem', borderRadius: 0, color: '#161616' }}
              >
                {ANTHROPIC_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
          </section>
        )}

        {/* ── Test Connection ──────────────────────────────────────── */}
        {testResult && (
          <InlineNotification
            kind={testResult.ok ? 'success' : 'error'}
            title={testResult.ok
              ? `Connected — ${testResult.latency_ms}ms`
              : 'Connection failed'}
            subtitle={testResult.ok
              ? (testResult.preview ? `Model responded: "${testResult.preview}"` : 'Model is responding.')
              : (testResult.error || 'Unknown error')}
            lowContrast
            style={{ marginBottom: '1rem' }}
            onCloseButtonClick={() => setTestResult(null)}
          />
        )}

        {saveSuccess && (
          <InlineNotification
            kind="success"
            title="Settings saved"
            subtitle="The active LLM provider will be used for all new normalization runs."
            lowContrast
            style={{ marginBottom: '1rem' }}
            onCloseButtonClick={() => setSaveSuccess(false)}
          />
        )}

        {saveError && (
          <InlineNotification
            kind="error"
            title="Save failed"
            subtitle={saveError}
            lowContrast
            style={{ marginBottom: '1rem' }}
            onCloseButtonClick={() => setSaveError('')}
          />
        )}

        {/* ── Action buttons ───────────────────────────────────────── */}
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          {testing ? (
            <InlineLoading description="Testing connection…" style={{ flex: 'none' }} />
          ) : (
            <Button kind="secondary" onClick={handleTest} disabled={saving}>
              Test connection
            </Button>
          )}
          {saving ? (
            <InlineLoading description="Saving…" style={{ flex: 'none' }} />
          ) : (
            <Button kind="primary" onClick={handleSave} disabled={testing}>
              Save settings
            </Button>
          )}
        </div>

        {/* ── Info footer ──────────────────────────────────────────── */}
        <div style={{ marginTop: '2.5rem', padding: '1rem', background: '#f4f4f4', borderLeft: '3px solid #0f62fe', fontSize: '0.8125rem', color: '#525252', lineHeight: 1.6 }}>
          <strong style={{ color: '#161616' }}>Security note:</strong> API keys are encrypted
          with AES-256 before being stored in PostgreSQL. They are never logged or returned in
          plaintext from any API endpoint. Set a strong <code>SECRET_KEY</code> in your
          <code>.env</code> file before using cloud providers in production.
        </div>
      </div>
    </>
  );
}
