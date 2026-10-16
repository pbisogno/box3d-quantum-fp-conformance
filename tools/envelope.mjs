// Laboratory-authored transport. Node standard library only.
import {createCipheriv, createDecipheriv, createHash, randomBytes} from 'node:crypto';
export const MANIFEST = '8d7708a1b7aeb04d2c91955d95392b77a8d7dd86762b7a34a8d3ed08efaf59ab';
export const sha256 = value => createHash('sha256').update(value).digest('hex');
export function decodeKey(value) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9+/]{43}=$/.test(value)) throw new Error('Invalid encryption key encoding');
  const key = Buffer.from(value, 'base64');
  if (key.length !== 32 || key.toString('base64') !== value) throw new Error('Invalid encryption key length');
  return key;
}
function domain(kind) {
  if (kind === 'payload') return ['BFPENC01', `BFP-PAYLOAD-V1:${MANIFEST}`];
  if (kind === 'results') return ['BFPRES01', `BFP-RESULTS-V1:${MANIFEST}`];
  throw new Error('Unknown envelope domain');
}
export function seal(plain, key, kind) {
  if (!Buffer.isBuffer(key) || key.length !== 32) throw new Error('Invalid encryption key');
  const [magic, aad] = domain(kind), nonce = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', key, nonce);
  cipher.setAAD(Buffer.from(aad, 'ascii'));
  const encrypted = Buffer.concat([cipher.update(plain), cipher.final()]);
  return Buffer.concat([Buffer.from(magic, 'ascii'), nonce, cipher.getAuthTag(), encrypted]);
}
export function open(envelope, key, kind) {
  const [magic, aad] = domain(kind);
  if (!Buffer.isBuffer(envelope) || envelope.length < 36 || envelope.subarray(0,8).toString('ascii') !== magic) throw new Error('Invalid encrypted envelope');
  const decipher = createDecipheriv('aes-256-gcm', key, envelope.subarray(8,20));
  decipher.setAAD(Buffer.from(aad, 'ascii')); decipher.setAuthTag(envelope.subarray(20,36));
  // Authentication completes before any plaintext is returned to a caller.
  return Buffer.concat([decipher.update(envelope.subarray(36)), decipher.final()]);
}
