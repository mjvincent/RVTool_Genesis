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
} from '@carbon/react';
import { Settings as SettingsIcon } from '@carbon/icons-react';
import { api, LLMProvider, LLMSettingsResponse, LLMSettingsSave } from '../api/client';

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

  // UI state
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; latency_ms?: number | null; preview?: string | null; error?: string | null } | null>(null);

  // ── load current settings ──────────────────────────────────────────────────
  useEffect(() => {
    api.settings.get().then((s: LLMSettingsResponse) => {
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
      setLoaded(true);
    }).catch(() => setLoaded(true));
  }, []);

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
      // refresh hints from server response
      setWxKeyHint(s.watsonx_api_key_hint);
      setOaiKeyHint(s.openai_api_key_hint);
      setAntKeyHint(s.anthropic_api_key_hint);
      // clear plaintext key fields after save
      setWxKey(''); setOaiKey(''); setAntKey('');
      setSaveSuccess(true);
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
