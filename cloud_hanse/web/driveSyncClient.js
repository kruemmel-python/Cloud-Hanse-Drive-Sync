(() => {
  const DEFAULT_FOLDER_URL = "https://drive.google.com/drive/folders/16O5AiugmonSzX1pfZ5a5bjZZ4Y_MoRCO";
  const DRIVE_API_BASE = "https://www.googleapis.com/drive/v3";

  function extractFolderId(folderUrl) {
    const match = folderUrl.match(/\/folders\/([a-zA-Z0-9_-]+)/);
    if (!match) {
      throw new Error(`Keine folder id in URL gefunden: ${folderUrl}`);
    }
    return match[1];
  }

  class DriveSyncClient {
    constructor({
      folderUrl = DEFAULT_FOLDER_URL,
      fileName = "world_state.json",
      apiKey = "",
      fileId = "",
      backendBase = "",
    } = {}) {
      this.folderUrl = folderUrl;
      this.folderId = extractFolderId(folderUrl);
      this.fileName = fileName;
      this.apiKey = apiKey;
      this.fileId = fileId;
      this.backendBase = backendBase || "";
    }

    async readWorldStatePublic() {
      if (this.apiKey) {
        const fileId = this.fileId || (await this.discoverFileIdByApi());
        this.fileId = fileId;
        const url = new URL(`${DRIVE_API_BASE}/files/${fileId}`);
        url.searchParams.set("alt", "media");
        url.searchParams.set("key", this.apiKey);
        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(`Drive read fehlgeschlagen: ${response.status}`);
        }
        return await response.json();
      }

      if (!this.fileId) {
        throw new Error("Public read ohne apiKey benoetigt eine bekannte fileId.");
      }
      const url = new URL("https://drive.google.com/uc");
      url.searchParams.set("export", "download");
      url.searchParams.set("id", this.fileId);
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Direktdownload fehlgeschlagen: ${response.status}`);
      }
      return await response.json();
    }

    async discoverFileIdByApi() {
      if (!this.apiKey) {
        throw new Error("discoverFileIdByApi benoetigt apiKey.");
      }
      const url = new URL(`${DRIVE_API_BASE}/files`);
      url.searchParams.set("key", this.apiKey);
      url.searchParams.set("q", `'${this.folderId}' in parents and trashed=false and name='${this.fileName}'`);
      url.searchParams.set("fields", "files(id,name,modifiedTime)");
      url.searchParams.set("orderBy", "modifiedTime desc");
      url.searchParams.set("pageSize", "5");
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Drive list fehlgeschlagen: ${response.status}`);
      }
      const body = await response.json();
      const first = body?.files?.[0];
      if (!first?.id) {
        throw new Error(`${this.fileName} wurde im Zielordner nicht gefunden.`);
      }
      return first.id;
    }

    async postTrade(action) {
      return this.#postBackend("/api/action/trade", action);
    }

    async postGuildAction(action) {
      return this.#postBackend("/api/action/guild", action);
    }

    async #postBackend(path, payload) {
      const response = await fetch(`${this.backendBase}${path}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      const body = await response.json();
      if (!response.ok) {
        throw new Error(body?.error || `Backend write fehlgeschlagen: ${response.status}`);
      }
      return body;
    }
  }

  window.DriveSyncClient = DriveSyncClient;
})();
