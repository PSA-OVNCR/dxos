<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import type { CollectionView, FieldView } from '../types'

type Data = Record<string, unknown>

const props = defineProps<{
  view: CollectionView
  modelValue: Data
  mode: 'create' | 'edit'
  requiredExtra?: string[]
}>()
const emit = defineEmits<{
  'update:modelValue': [value: Data]
  submit: [payload: Data]
}>()

const uid = useId()
const inputId = (name: string): string => `${uid}-${name}`

/** Trường số thứ tự do lõi cấp nên không có ô nhập. */
const fields = computed(() => Object.entries(props.view.fields).filter(([, f]) => f.type !== 'sequence'))

const values = ref<Data>({ ...props.modelValue })
// Ảnh chụp dữ liệu gốc và tập trường người dùng đã chạm tới: nền để chỉ gửi phần thay đổi (không gửi lại PII đã che).
let original: Data = { ...props.modelValue }
const touched = new Set<string>()

function sameData(a: Data, b: Data): boolean {
  const ka = Object.keys(a)
  return ka.length === Object.keys(b).length && ka.every((k) => Object.hasOwn(b, k) && Object.is(a[k], b[k]))
}

function reset(from: Data): void {
  values.value = { ...from }
  original = { ...from }
  touched.clear()
}

// Dữ liệu từ ngoài đổi sang bản ghi khác thì lấy làm nền mới; giá trị vừa phát ra rồi quay lại (v-model) thì bỏ qua.
watch(() => props.modelValue, (mv) => { if (!sameData(mv, values.value)) reset(mv) })
watch(() => props.view, () => { reset(props.modelValue) })

function isRequired(name: string, f: FieldView): boolean {
  return f.required || (props.requiredExtra?.includes(name) ?? false)
}

function set(name: string, v: unknown): void {
  values.value = { ...values.value, [name]: v }
  touched.add(name)
  emit('update:modelValue', { ...values.value })
}

function onText(name: string, ev: Event): void {
  set(name, (ev.target as HTMLInputElement).value)
}

function onBool(name: string, ev: Event): void {
  set(name, (ev.target as HTMLInputElement).checked)
}

function onInt(name: string, ev: Event): void {
  const el = ev.target as HTMLInputElement
  const raw = el.value
  const n = el.valueAsNumber
  if (raw === '') {
    el.setCustomValidity('')
    set(name, '')
  } else if (Number.isSafeInteger(n)) {
    el.setCustomValidity('')
    set(name, n)
  } else {
    // Không ép kiểu lặng lẽ: số thập phân và số nguyên vượt giới hạn an toàn của JS đều làm biểu mẫu không hợp lệ.
    el.setCustomValidity(/^-?\d+$/.test(raw) ? 'Số nguyên quá lớn để gửi an toàn' : 'Phải là số nguyên')
    set(name, raw)
  }
}

function display(name: string): string {
  const v = values.value[name]
  return v === undefined || v === null ? '' : String(v)
}

function isEmpty(v: unknown): boolean {
  return v === undefined || v === null || v === ''
}

function norm(f: FieldView, v: unknown): unknown {
  if (f.type === 'boolean') return v === true
  return isEmpty(v) ? '' : v
}

function payload(): Data {
  const out: Data = {}
  for (const [name, f] of fields.value) {
    const v = values.value[name]
    if (props.mode === 'edit') {
      if (!touched.has(name) || Object.is(norm(f, v), norm(f, original[name]))) continue
      out[name] = f.type === 'boolean' ? v === true : isEmpty(v) ? null : v
    } else if (f.type === 'boolean') {
      if (v === true || touched.has(name) || isRequired(name, f)) out[name] = v === true
    } else if (!isEmpty(v)) {
      out[name] = v
    }
  }
  return out
}

function onSubmit(ev: Event): void {
  const form = ev.currentTarget as HTMLFormElement
  if (!form.checkValidity()) {
    form.reportValidity()
    return
  }
  emit('submit', payload())
}
</script>

<template>
  <form class="dx-record-form" @submit.prevent="onSubmit">
    <div v-for="[name, f] in fields" :key="name" class="dx-field">
      <label :for="inputId(name)">{{ f.label ?? name }}<span v-if="isRequired(name, f) && f.type !== 'boolean'" aria-hidden="true"> *</span></label>
      <input
        v-if="f.type === 'boolean'"
        :id="inputId(name)"
        type="checkbox"
        :name="name"
        :checked="values[name] === true"
        :aria-describedby="f.pii ? `${inputId(name)}-pii` : undefined"
        @change="onBool(name, $event)"
      >
      <input
        v-else-if="f.type === 'integer'"
        :id="inputId(name)"
        type="number"
        step="1"
        :name="name"
        :value="display(name)"
        :required="isRequired(name, f)"
        :aria-describedby="f.pii ? `${inputId(name)}-pii` : undefined"
        @input="onInt(name, $event)"
      >
      <input
        v-else
        :id="inputId(name)"
        :type="f.type === 'date' ? 'date' : 'text'"
        :name="name"
        :value="display(name)"
        :required="isRequired(name, f)"
        :autocomplete="f.pii ? 'off' : undefined"
        :aria-describedby="f.pii ? `${inputId(name)}-pii` : undefined"
        @input="onText(name, $event)"
      >
      <small v-if="f.pii" :id="`${inputId(name)}-pii`" class="dx-pii-note">dữ liệu cá nhân</small>
    </div>
    <slot name="actions">
      <button type="submit">{{ mode === 'create' ? 'Tạo' : 'Lưu' }}</button>
    </slot>
  </form>
</template>
