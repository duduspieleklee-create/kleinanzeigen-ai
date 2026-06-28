{{/*
Expand the name of the chart.
*/}}
{{- define "kleinanzeigen-worker.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "kleinanzeigen-worker.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "kleinanzeigen-worker.labels" -}}
helm.sh/chart: {{ include "kleinanzeigen-worker.name" . }}-{{ .Chart.Version | replace "+" "_" }}
{{ include "kleinanzeigen-worker.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "kleinanzeigen-worker.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kleinanzeigen-worker.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
