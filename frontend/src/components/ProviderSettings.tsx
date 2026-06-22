import React, { useEffect, useState } from 'react';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

interface Provider {
  id: string;
  label: string;
  base_url: string;
  base_url_default: string;
  base_url_editable: boolean;
  model: string;
  default_model: string;
  models: string[];
  key_required: boolean;
  key_example: string;
  key_url: string;
  key_set: boolean;
  is_active: boolean;
}

const ProviderSettings: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [active, setActive] = useState('');
  const [selected, setSelected] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [model, setModel] = useState('');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const [dynModels, setDynModels] = useState<string[]>([]);
  const [modelMsg, setModelMsg] = useState('');
  const [fetchingModels, setFetchingModels] = useState(false);
  const [customModel, setCustomModel] = useState(false);

  const pick = (list: Provider[], id: string) => {
    const p = list.find((x) => x.id === id);
    if (!p) return;
    setSelected(id);
    setApiKey('');
    setBaseUrl(p.base_url);
    setModel(p.model);
    setDynModels([]);
    setModelMsg('');
    setCustomModel(false);
  };

  const fetchModels = async (id?: string, key?: string, url?: string) => {
    const provider = id || selected;
    if (!provider) return;
    setFetchingModels(true);
    setModelMsg('Fetching models…');
    try {
      const body: any = { provider, base_url: url ?? baseUrl };
      const k = key ?? apiKey;
      if (k) body.api_key = k;
      const r = await fetch(`${API_BASE_URL}/api/providers/models`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.message || 'Failed to fetch models');
      const list: string[] = d.models || [];
      setDynModels(list);
      setModel((cur) => (cur && list.includes(cur) ? cur : list[0] || cur));
      setModelMsg(
        d.source === 'live'
          ? `✓ ${list.length} models from provider`
          : `⚠ provider unreachable — showing examples`
      );
    } catch (e: any) {
      setModelMsg(`✗ ${e.message}`);
    } finally {
      setFetchingModels(false);
    }
  };

  const load = async () => {
    try {
      const r = await fetch(`${API_BASE_URL}/api/providers`);
      const d = await r.json();
      setProviders(d.providers);
      setActive(d.active);
      pick(d.providers, selected || d.active);
    } catch (e: any) {
      setStatus(`✗ Could not load providers: ${e.message}`);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const current = providers.find((p) => p.id === selected);

  // When a provider that already has a key (or needs none) is selected, fetch
  // its live model list automatically using the stored credentials.
  useEffect(() => {
    if (current && (current.key_set || !current.key_required)) {
      fetchModels(current.id, undefined, current.base_url);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  const modelOptions = dynModels.length ? dynModels : current?.models || [];

  const save = async (activate: boolean) => {
    setBusy(true);
    setStatus('');
    try {
      const body: any = { provider: selected, base_url: baseUrl, model, activate };
      if (apiKey) body.api_key = apiKey;
      const r = await fetch(`${API_BASE_URL}/api/providers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.message || 'Save failed');
      setProviders(d.providers);
      setActive(d.active);
      setApiKey('');
      setStatus(activate ? `✓ Activated ${selected}` : `✓ Saved ${selected}`);
    } catch (e: any) {
      setStatus(`✗ ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const test = async () => {
    setBusy(true);
    setStatus('Testing the active provider…');
    try {
      const r = await fetch(`${API_BASE_URL}/api/providers/test`, { method: 'POST' });
      const d = await r.json();
      setStatus(d.ok ? `✓ Provider responded: ${d.message}` : `✗ ${d.message}`);
    } catch (e: any) {
      setStatus(`✗ ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-panel" onClick={(e) => e.stopPropagation()}>
        <div className="settings-header">
          <h2>LLM Provider &amp; Model</h2>
          <button className="settings-close" onClick={onClose} aria-label="Close settings">
            ×
          </button>
        </div>

        <p className="settings-active">
          Active: <strong>{active || '—'}</strong>
        </p>

        <label>Provider</label>
        <select value={selected} onChange={(e) => pick(providers, e.target.value)}>
          {providers.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
              {p.key_set ? ' ✓' : ''}
              {p.is_active ? ' — active' : ''}
            </option>
          ))}
        </select>

        {current && (
          <>
            <label>
              API Key{current.key_required ? '' : ' (optional)'}
              {current.key_set ? ' — set; leave blank to keep' : ''}
            </label>
            <input
              type="password"
              placeholder={current.key_example}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              autoComplete="off"
            />
            <a href={current.key_url} target="_blank" rel="noreferrer" className="settings-hint">
              Where do I get a key? ↗
            </a>
            {current.key_required && (
              <button
                type="button"
                className="settings-link-btn"
                disabled={fetchingModels || (!apiKey && !current.key_set)}
                onClick={() => fetchModels()}
              >
                ↻ Load available models with this key
              </button>
            )}

            <label>Model</label>
            <div className="settings-row">
              <select
                value={customModel || !modelOptions.includes(model) ? '__custom__' : model}
                onChange={(e) => {
                  if (e.target.value === '__custom__') {
                    setCustomModel(true);
                  } else {
                    setCustomModel(false);
                    setModel(e.target.value);
                  }
                }}
              >
                {modelOptions.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
                <option value="__custom__">Custom…</option>
              </select>
              <button
                type="button"
                className="settings-refresh"
                disabled={fetchingModels}
                onClick={() => fetchModels()}
                title="Fetch live models from the provider"
              >
                {fetchingModels ? '…' : '↻'}
              </button>
            </div>
            {(customModel || !modelOptions.includes(model)) && (
              <input
                className="settings-custom-model"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder={`custom model (e.g. ${current.default_model})`}
              />
            )}
            <span className="settings-hint">
              {modelMsg || `${modelOptions.length} model(s) available`}
            </span>

            {current.base_url_editable && (
              <>
                <label>Base URL</label>
                <input
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder={current.base_url_default}
                />
                <span className="settings-hint">default: {current.base_url_default}</span>
              </>
            )}

            <div className="settings-actions">
              <button className="button-primary" disabled={busy} onClick={() => save(true)}>
                Save &amp; Activate
              </button>
              <button disabled={busy} onClick={() => save(false)}>
                Save only
              </button>
              <button disabled={busy} onClick={test}>
                Test active
              </button>
            </div>
            {status && <p className="settings-status">{status}</p>}
          </>
        )}
      </div>
    </div>
  );
};

export default ProviderSettings;
