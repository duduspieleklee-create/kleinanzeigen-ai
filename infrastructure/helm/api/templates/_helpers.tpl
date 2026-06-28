{{/*
Expand the name of the chart.
*/}}
{{- define "kleinanzeigen-api.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "kleinanzeigen-api.fullname" -}}
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
{{- define "kleinanzeigen-api.labels" -}}
helm.sh/chart: {{ include "kleinanzeigen-api.name" . }}-{{ .Chart.Version | replace "+" "_" }}
{{ include "kleinanzeigen-api.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "kleinanzeigen-api.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kleinanzeigen-api.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
