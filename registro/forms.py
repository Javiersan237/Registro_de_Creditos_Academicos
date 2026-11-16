from django import forms
from django.contrib.auth import get_user_model

from .context import GRUPO_PROFESOR
from .models import CARRERAS, Conferencia

AYUDA_PREGUNTAS = ("Una pregunta por renglón: Pregunta | opción | opción | opción. "
                   "Marca la correcta con * al inicio. Ejemplo: ¿Qué lenguaje se usó? | *Python | Cobol | Pascal")


class ConferenciaForm(forms.ModelForm):
    carreras_sel = forms.MultipleChoiceField(label="Carreras participantes", choices=CARRERAS,
                                             widget=forms.CheckboxSelectMultiple,
                                             initial=[c for c, _ in CARRERAS])
    preguntas = forms.CharField(label="Cuestionario", widget=forms.Textarea(attrs={"rows": 6}),
                                help_text=AYUDA_PREGUNTAS)

    class Meta:
        model = Conferencia
        fields = ["nombre", "lugar", "fecha", "hora_inicio", "hora_fin", "creditos", "profesor"]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}),
            "hora_inicio": forms.TimeInput(attrs={"type": "time"}),
            "hora_fin": forms.TimeInput(attrs={"type": "time"}),
        }
        labels = {"creditos": "Créditos asignados (máx. 2)", "profesor": "Profesor designado"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["profesor"].queryset = get_user_model().objects.filter(groups__name=GRUPO_PROFESOR)
        self.fields["profesor"].required = True
        self.fields["profesor"].label_from_instance = lambda u: u.get_full_name() or u.username

    def clean_preguntas(self):
        resultado = []
        for n, linea in enumerate([l for l in self.cleaned_data["preguntas"].splitlines() if l.strip()], 1):
            partes = [p.strip() for p in linea.split("|")]
            texto, opciones = partes[0], [o for o in partes[1:] if o]
            if not texto or len(opciones) < 2:
                raise forms.ValidationError(f"Renglón {n}: escribe la pregunta y al menos 2 opciones separadas por |.")
            correctas = [i for i, o in enumerate(opciones) if o.startswith("*")]
            if len(correctas) != 1:
                raise forms.ValidationError(f"Renglón {n}: marca exactamente una opción correcta con *.")
            resultado.append((texto, [o.lstrip("*").strip() for o in opciones], correctas[0]))
        if not resultado:
            raise forms.ValidationError("El cuestionario necesita al menos una pregunta.")
        return resultado

    def clean_creditos(self):
        c = self.cleaned_data["creditos"]
        if c > 2:
            raise forms.ValidationError("Una actividad no puede otorgar más de 2 créditos (RN-03).")
        return c


class PadronForm(forms.Form):
    archivo = forms.FileField(label="Archivo CSV del padrón")
