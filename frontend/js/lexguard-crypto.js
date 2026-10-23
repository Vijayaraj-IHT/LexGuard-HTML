/**
 * LexGuard — Client-Side Cryptographic Verifier (lexguard-crypto.js)
 * Web Crypto API SHA-256 zero-upload hash generator
 * Semester 5 Project · LexGuard Judicial Repository & Verification Platform
 */

(function (window) {
  'use strict';

  window.LG = window.LG || {};

  LG.crypto = {
    /**
     * Computes SHA-256 cryptographic digest of a File, Blob, or ArrayBuffer
     * completely client-side in the browser using the Web Crypto API.
     * Zero bytes are sent over the network.
     *
     * @param {File|Blob|ArrayBuffer} data
     * @param {Function} [progressCallback] - Optional callback(percent)
     * @returns {Promise<string>} 64-character lowercase hex digest
     */
    sha256: function (data, progressCallback) {
      return new Promise(function (resolve, reject) {
        if (!window.crypto || !window.crypto.subtle) {
          reject(new Error('Web Crypto API is not supported in this browser environment.'));
          return;
        }

        if (data instanceof ArrayBuffer) {
          window.crypto.subtle.digest('SHA-256', data)
            .then(function (hashBuffer) {
              resolve(LG.crypto.bufferToHex(hashBuffer));
            })
            .catch(reject);
          return;
        }

        if (data instanceof Blob || data instanceof File) {
          const reader = new FileReader();

          reader.onprogress = function (e) {
            if (e.lengthComputable && typeof progressCallback === 'function') {
              const percent = Math.round((e.loaded / e.total) * 100);
              progressCallback(percent);
            }
          };

          reader.onload = function (e) {
            const arrayBuffer = e.target.result;
            if (typeof progressCallback === 'function') progressCallback(100);

            window.crypto.subtle.digest('SHA-256', arrayBuffer)
              .then(function (hashBuffer) {
                const hexString = LG.crypto.bufferToHex(hashBuffer);
                resolve(hexString);
              })
              .catch(reject);
          };

          reader.onerror = function (e) {
            reject(new Error('Failed to read file: ' + (e.target.error ? e.target.error.message : 'Unknown error')));
          };

          reader.readAsArrayBuffer(data);
          return;
        }

        // If string
        if (typeof data === 'string') {
          const encoder = new TextEncoder();
          const encoded = encoder.encode(data);
          window.crypto.subtle.digest('SHA-256', encoded)
            .then(function (hashBuffer) {
              resolve(LG.crypto.bufferToHex(hashBuffer));
            })
            .catch(reject);
          return;
        }

        reject(new Error('Unsupported data type for SHA-256 hashing'));
      });
    },

    /**
     * Converts an ArrayBuffer to a lowercase hex string.
     */
    bufferToHex: function (buffer) {
      const byteArray = new Uint8Array(buffer);
      let hexString = '';
      for (let i = 0; i < byteArray.length; i++) {
        const hex = byteArray[i].toString(16).padStart(2, '0');
        hexString += hex;
      }
      return hexString.toLowerCase();
    },

    /**
     * Formats a 64-character hash into 8-character blocks separated by spaces
     * for easy human verification.
     */
    formatHashBlocks: function (hash) {
      if (!hash || hash.length !== 64) return hash;
      const chunks = [];
      for (let i = 0; i < 64; i += 8) {
        chunks.push(hash.substring(i, i + 8));
      }
      return chunks.join(' ');
    }
  };

})(window);
