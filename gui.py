import threading
import customtkinter as ctk
import api_football as fb
import modelo
import nivel

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("FutNeural — Bot Preditivo Copa 2026")
        self.geometry("960x640")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._modelo = None
        self._scaler = None
        self._n_amostras = 0
        self._nome_modelo = ""

        self._criar_sidebar()
        self._criar_frames()
        self._mostrar_frame("previsao")
        self._carregar_modelo()
        self._atualizar_status_apis()
        self._atualizar_nivel_label()

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------
    def _criar_sidebar(self):
        sb = ctk.CTkFrame(self, width=200, corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_rowconfigure(5, weight=1)

        ctk.CTkLabel(
            sb, text="FutNeural IA",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=0, padx=20, pady=(20, 30))

        botoes = [
            ("Nova Previsao", lambda: self._mostrar_frame("previsao")),
            ("Jogos da Copa", lambda: self._mostrar_frame("copa")),
            ("Resultados", lambda: self._mostrar_frame("resultados")),
            ("Tabela de Grupos", lambda: self._mostrar_frame("tabela")),
            ("Status APIs", lambda: self._mostrar_frame("status")),
        ]
        for i, (texto, cmd) in enumerate(botoes, start=1):
            ctk.CTkButton(sb, text=texto, command=cmd).grid(
                row=i, column=0, padx=20, pady=8
            )

        self._lbl_nivel = ctk.CTkLabel(sb, text="", font=ctk.CTkFont(size=12, weight="bold"))
        self._lbl_nivel.grid(row=6, column=0, padx=10, pady=(10, 2), sticky="s")

        self._lbl_status = ctk.CTkLabel(sb, text="", font=ctk.CTkFont(size=11))
        self._lbl_status.grid(row=7, column=0, padx=10, pady=(2, 10), sticky="s")

    # ------------------------------------------------------------------
    # Frames
    # ------------------------------------------------------------------
    def _criar_frames(self):
        self._frames = {}
        self._frames["previsao"] = self._criar_frame_previsao()
        self._frames["copa"] = self._criar_frame_copa()
        self._frames["resultados"] = self._criar_frame_resultados()
        self._frames["tabela"] = self._criar_frame_tabela()
        self._frames["status"] = self._criar_frame_status()

    def _mostrar_frame(self, nome):
        for f in self._frames.values():
            f.grid_forget()
        self._frames[nome].grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        if nome == "status":
            self._atualizar_status_apis()

    # ------------------------------------------------------------------
    # Frame: Nova Previsao
    # ------------------------------------------------------------------
    def _criar_frame_previsao(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")

        ctk.CTkLabel(
            frame, text="Analise de Confronto",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(pady=(20, 20))

        inputs = ctk.CTkFrame(frame, fg_color="transparent")
        inputs.pack(pady=10)

        self._entry_casa = ctk.CTkEntry(
            inputs, placeholder_text="Equipa Casa (ex: Brasil)", width=250, height=40
        )
        self._entry_casa.grid(row=0, column=0, padx=10)

        ctk.CTkLabel(
            inputs, text="VS", font=ctk.CTkFont(size=18, weight="bold")
        ).grid(row=0, column=1, padx=10)

        self._entry_fora = ctk.CTkEntry(
            inputs, placeholder_text="Equipa Fora (ex: Argentina)", width=250, height=40
        )
        self._entry_fora.grid(row=0, column=2, padx=10)

        self._btn_prever = ctk.CTkButton(
            frame, text="Gerar Previsao", height=40,
            font=ctk.CTkFont(weight="bold"),
            command=self._iniciar_previsao,
        )
        self._btn_prever.pack(pady=15)

        self._progress = ctk.CTkProgressBar(frame, width=400, mode="indeterminate")

        cards = ctk.CTkFrame(frame)
        cards.pack(pady=15, padx=20, fill="both", expand=True)
        cards.columnconfigure((0, 1, 2), weight=1)

        self._lbl_pc = ctk.CTkLabel(cards, text="Vitoria Casa\n--%", font=ctk.CTkFont(size=18))
        self._lbl_pc.grid(row=0, column=0, pady=20, padx=10)
        self._lbl_pe = ctk.CTkLabel(cards, text="Empate\n--%", font=ctk.CTkFont(size=18))
        self._lbl_pe.grid(row=0, column=1, pady=20, padx=10)
        self._lbl_pf = ctk.CTkLabel(cards, text="Vitoria Fora\n--%", font=ctk.CTkFont(size=18))
        self._lbl_pf.grid(row=0, column=2, pady=20, padx=10)

        self._lbl_detalhes = ctk.CTkLabel(
            cards, text="Aguardando dados...",
            font=ctk.CTkFont(size=13), wraplength=700,
        )
        self._lbl_detalhes.grid(row=1, column=0, columnspan=3, pady=(5, 0), padx=10)

        self._txt_mercados = ctk.CTkTextbox(
            frame, width=700, height=280,
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self._txt_mercados.pack(pady=(5, 10), padx=20, fill="both", expand=True)

        return frame

    def _iniciar_previsao(self):
        casa = self._entry_casa.get().strip()
        fora = self._entry_fora.get().strip()
        if not casa or not fora:
            self._lbl_detalhes.configure(text="Preencha os dois times.", text_color="red")
            return

        self._btn_prever.configure(state="disabled", text="Calculando...")
        self._progress.pack(pady=5)
        self._progress.start()
        self._lbl_detalhes.configure(text="Buscando estatisticas na API...", text_color="white")

        threading.Thread(
            target=self._executar_previsao, args=(casa, fora), daemon=True
        ).start()

    def _executar_previsao(self, casa, fora):
        try:
            r = modelo.realizar_previsao(
                casa, fora,
                self._modelo, self._scaler, self._n_amostras, self._nome_modelo,
            )
            self.after(0, self._exibir_previsao, r)
        except Exception as e:
            self.after(0, self._erro_previsao, str(e))

    def _exibir_previsao(self, r):
        self._progress.stop()
        self._progress.pack_forget()
        self._btn_prever.configure(state="normal", text="Gerar Previsao")

        self._lbl_pc.configure(
            text=f"Vitoria Casa\n{r['prob_casa']*100:.1f}%", text_color="#2ecc71"
        )
        self._lbl_pe.configure(
            text=f"Empate\n{r['prob_empate']*100:.1f}%", text_color="#f1c40f"
        )
        self._lbl_pf.configure(
            text=f"Vitoria Fora\n{r['prob_fora']*100:.1f}%", text_color="#e74c3c"
        )

        self._lbl_detalhes.configure(
            text=f"Modelo: {r['modelo_usado']}  |  Fonte: {r['fonte_casa']}",
            text_color="gray",
        )

        self._txt_mercados.delete("0.0", "end")
        self._txt_mercados.insert("end", modelo.formatar_previsao_texto(r))

    def _erro_previsao(self, msg):
        self._progress.stop()
        self._progress.pack_forget()
        self._btn_prever.configure(state="normal", text="Gerar Previsao")
        self._lbl_detalhes.configure(text=f"Erro: {msg}", text_color="red")

    # ------------------------------------------------------------------
    # Frame: Jogos da Copa 2026 (dados locais)
    # ------------------------------------------------------------------
    def _criar_frame_copa(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")

        ctk.CTkLabel(
            frame, text="Jogos da Copa 2026",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(pady=(20, 5))

        ctk.CTkLabel(
            frame,
            text="Registre aqui os resultados reais da Copa para melhorar as previsoes.",
            font=ctk.CTkFont(size=13),
        ).pack(pady=(0, 15))

        entrada = ctk.CTkFrame(frame, fg_color="transparent")
        entrada.pack(pady=10)

        ctk.CTkLabel(entrada, text="Casa:").grid(row=0, column=0, padx=5)
        self._copa_casa = ctk.CTkEntry(entrada, width=160, placeholder_text="Ex: Brazil")
        self._copa_casa.grid(row=0, column=1, padx=5)

        ctk.CTkLabel(entrada, text="Gols:").grid(row=0, column=2, padx=5)
        self._copa_gols_casa = ctk.CTkEntry(entrada, width=50)
        self._copa_gols_casa.grid(row=0, column=3, padx=5)

        ctk.CTkLabel(entrada, text="x").grid(row=0, column=4, padx=5)

        self._copa_gols_fora = ctk.CTkEntry(entrada, width=50)
        self._copa_gols_fora.grid(row=0, column=5, padx=5)

        ctk.CTkLabel(entrada, text="Fora:").grid(row=0, column=6, padx=5)
        self._copa_fora = ctk.CTkEntry(entrada, width=160, placeholder_text="Ex: Serbia")
        self._copa_fora.grid(row=0, column=7, padx=5)

        stats_frame = ctk.CTkFrame(frame, fg_color="transparent")
        stats_frame.pack(pady=5)

        ctk.CTkLabel(stats_frame, text="Escanteios Casa:").grid(row=0, column=0, padx=3)
        self._copa_esc_casa = ctk.CTkEntry(stats_frame, width=40, placeholder_text="0")
        self._copa_esc_casa.grid(row=0, column=1, padx=3)

        ctk.CTkLabel(stats_frame, text="Fora:").grid(row=0, column=2, padx=3)
        self._copa_esc_fora = ctk.CTkEntry(stats_frame, width=40, placeholder_text="0")
        self._copa_esc_fora.grid(row=0, column=3, padx=3)

        ctk.CTkLabel(stats_frame, text="Cartoes Casa:").grid(row=0, column=4, padx=3)
        self._copa_cart_casa = ctk.CTkEntry(stats_frame, width=40, placeholder_text="0")
        self._copa_cart_casa.grid(row=0, column=5, padx=3)

        ctk.CTkLabel(stats_frame, text="Fora:").grid(row=0, column=6, padx=3)
        self._copa_cart_fora = ctk.CTkEntry(stats_frame, width=40, placeholder_text="0")
        self._copa_cart_fora.grid(row=0, column=7, padx=3)

        ctk.CTkButton(
            frame, text="Registrar Resultado",
            command=self._registrar_copa,
        ).pack(pady=10)

        self._copa_log = ctk.CTkTextbox(frame, width=700, height=300,
                                         font=ctk.CTkFont(family="Consolas", size=13))
        self._copa_log.pack(pady=10, padx=20, fill="both", expand=True)

        self._atualizar_lista_copa()
        return frame

    def _registrar_copa(self):
        casa = self._copa_casa.get().strip()
        fora = self._copa_fora.get().strip()
        try:
            gc = int(self._copa_gols_casa.get())
            gf = int(self._copa_gols_fora.get())
        except ValueError:
            self._copa_log.insert("end", "Gols devem ser numeros inteiros.\n")
            return

        if not casa or not fora:
            self._copa_log.insert("end", "Preencha os nomes dos dois times.\n")
            return

        esc_c = int(self._copa_esc_casa.get() or 0)
        esc_f = int(self._copa_esc_fora.get() or 0)
        cart_c = int(self._copa_cart_casa.get() or 0)
        cart_f = int(self._copa_cart_fora.get() or 0)

        fb.registrar_resultado_copa(casa, fora, gc, gf, esc_c, esc_f, cart_c, cart_f)
        self._copa_log.insert("end",
            f"Registrado: {casa} {gc} x {gf} {fora} "
            f"(esc: {esc_c}-{esc_f}, cart: {cart_c}-{cart_f})\n"
        )

        for entry in [self._copa_casa, self._copa_fora, self._copa_gols_casa,
                       self._copa_gols_fora, self._copa_esc_casa, self._copa_esc_fora,
                       self._copa_cart_casa, self._copa_cart_fora]:
            entry.delete(0, "end")

    def _atualizar_lista_copa(self):
        jogos = fb._carregar_copa_csv()
        if not jogos:
            self._copa_log.insert("end", "Nenhum jogo da Copa registrado ainda.\n"
                                  "Registre os resultados acima para que as previsoes\n"
                                  "usem dados reais do torneio em vez de historico antigo.\n")
            return

        self._copa_log.insert("end", f"{'Data':<12} {'Casa':<20} {'Placar':>7}  {'Fora':<20}\n")
        self._copa_log.insert("end", "-" * 62 + "\n")
        for j in jogos:
            placar = f"{j['Gols_Casa']} x {j['Gols_Fora']}"
            self._copa_log.insert(
                "end",
                f"{j['Data']:<12} {j['Casa']:<20} {placar:>7}  {j['Fora']:<20}\n"
            )

    # ------------------------------------------------------------------
    # Frame: Resultados
    # ------------------------------------------------------------------
    def _criar_frame_resultados(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")

        ctk.CTkLabel(
            frame, text="Resultados e Previsoes",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(pady=(20, 10))

        self._btn_sincronizar = ctk.CTkButton(
            frame, text="Sincronizar Resultados (API)",
            command=self._iniciar_sincronizacao,
        )
        self._btn_sincronizar.pack(pady=10)

        self._txt_resultados = ctk.CTkTextbox(frame, width=700, height=300)
        self._txt_resultados.pack(pady=10, padx=20, fill="both", expand=True)

        manual_frame = ctk.CTkFrame(frame, fg_color="transparent")
        manual_frame.pack(pady=10)

        ctk.CTkLabel(manual_frame, text="Fechar manualmente — ID:").grid(row=0, column=0, padx=5)
        self._entry_id_manual = ctk.CTkEntry(manual_frame, width=60)
        self._entry_id_manual.grid(row=0, column=1, padx=5)

        ctk.CTkLabel(manual_frame, text="Gols Casa:").grid(row=0, column=2, padx=5)
        self._entry_gols_casa = ctk.CTkEntry(manual_frame, width=50)
        self._entry_gols_casa.grid(row=0, column=3, padx=5)

        ctk.CTkLabel(manual_frame, text="Gols Fora:").grid(row=0, column=4, padx=5)
        self._entry_gols_fora = ctk.CTkEntry(manual_frame, width=50)
        self._entry_gols_fora.grid(row=0, column=5, padx=5)

        ctk.CTkButton(
            manual_frame, text="Fechar", width=80,
            command=self._fechar_manual,
        ).grid(row=0, column=6, padx=10)

        return frame

    def _iniciar_sincronizacao(self):
        self._btn_sincronizar.configure(state="disabled", text="Sincronizando...")
        self._txt_resultados.delete("0.0", "end")

        def callback_log(msg):
            self.after(0, lambda m=msg: self._append_resultado(m))

        def worker():
            try:
                log, manuais = modelo.fechar_resultados(callback_log=callback_log)
                if manuais:
                    nomes = [f"  ID {m['id']}: {m['casa']} x {m['fora']}" for m in manuais]
                    self.after(0, lambda: self._append_resultado(
                        "\nPendentes (informe o placar manualmente abaixo):\n" + "\n".join(nomes)
                    ))
            except Exception as e:
                self.after(0, lambda: self._append_resultado(f"Erro: {e}"))
            finally:
                self.after(0, lambda: self._btn_sincronizar.configure(
                    state="normal", text="Sincronizar Resultados (API)"
                ))
                self.after(0, self._atualizar_nivel_label)

        threading.Thread(target=worker, daemon=True).start()

    def _append_resultado(self, msg):
        self._txt_resultados.insert("end", msg + "\n")

    def _fechar_manual(self):
        try:
            idx = int(self._entry_id_manual.get()) - 1
            gc = int(self._entry_gols_casa.get())
            gf = int(self._entry_gols_fora.get())
        except ValueError:
            self._append_resultado("Valores invalidos. Informe numeros inteiros.")
            return

        try:
            modelo.fechar_resultado_manual(idx, gc, gf)
            self._append_resultado(f"ID {idx+1} fechado manualmente: {gc} x {gf}")
            self._atualizar_nivel_label()
        except Exception as e:
            self._append_resultado(f"Erro ao fechar: {e}")

    # ------------------------------------------------------------------
    # Frame: Tabela de Grupos
    # ------------------------------------------------------------------
    def _criar_frame_tabela(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")

        ctk.CTkLabel(
            frame, text="Tabela de Grupos — Copa 2026",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(pady=(20, 10))

        self._btn_tabela = ctk.CTkButton(
            frame, text="Carregar Tabela",
            command=self._carregar_tabela,
        )
        self._btn_tabela.pack(pady=10)

        self._txt_tabela = ctk.CTkTextbox(
            frame, width=700, height=400, font=ctk.CTkFont(family="Consolas", size=13)
        )
        self._txt_tabela.pack(pady=10, padx=20, fill="both", expand=True)

        return frame

    def _carregar_tabela(self):
        self._btn_tabela.configure(state="disabled", text="Carregando...")
        self._txt_tabela.delete("0.0", "end")

        def worker():
            try:
                grupos = fb.obter_tabela_grupos()
                if not grupos:
                    self.after(0, lambda: self._txt_tabela.insert(
                        "end", "Tabela ainda nao disponivel.\n"
                    ))
                    return

                linhas = []
                for grupo in grupos:
                    if not grupo:
                        continue
                    nome_grupo = grupo[0].get("group", "Grupo")
                    linhas.append(f"\n{nome_grupo}")
                    linhas.append(
                        f"{'Selecao':<22}{'Pts':>4}{'V':>4}{'E':>4}{'D':>4}{'GP':>5}{'GC':>5}"
                    )
                    for linha in grupo:
                        nome = linha["team"]["name"]
                        s = linha["all"]
                        linhas.append(
                            f"{nome:<22}{linha['points']:>4}"
                            f"{s['win']:>4}{s['draw']:>4}{s['lose']:>4}"
                            f"{s['goals']['for']:>5}{s['goals']['against']:>5}"
                        )

                texto = "\n".join(linhas)
                self.after(0, lambda: self._txt_tabela.insert("end", texto))

            except Exception as e:
                self.after(0, lambda: self._txt_tabela.insert("end", f"Erro: {e}\n"))
            finally:
                self.after(0, lambda: self._btn_tabela.configure(
                    state="normal", text="Carregar Tabela"
                ))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Frame: Status APIs
    # ------------------------------------------------------------------
    def _criar_frame_status(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")

        ctk.CTkLabel(
            frame, text="Status das APIs",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(pady=(20, 20))

        self._txt_status = ctk.CTkTextbox(frame, width=600, height=300)
        self._txt_status.pack(pady=10, padx=20, fill="both", expand=True)

        ctk.CTkButton(
            frame, text="Atualizar", command=self._atualizar_status_apis
        ).pack(pady=10)

        return frame

    def _atualizar_status_apis(self):
        self._txt_status.delete("0.0", "end")

        def worker():
            linhas = []

            import config as cfg
            if fb.chave_configurada():
                origem = fb.origem_chave() or "desconhecida"
                linhas.append(f"FOOTBALL_API_KEY: configurada (origem: {origem})")
                try:
                    status = fb.consultar_status_conta()
                    conta = status.get("subscription", {})
                    cota = status.get("requests", {})
                    linhas.append(
                        f"  Plano: {conta.get('plan')} | "
                        f"Requisicoes hoje: {cota.get('current')}/{cota.get('limit_day')}"
                    )
                except fb.FootballAPIError as e:
                    linhas.append(f"  Erro ao consultar status: {e}")
            else:
                linhas.append("FOOTBALL_API_KEY: NAO configurada")

            linhas.append("")
            if cfg.GROQ_API_KEY:
                linhas.append("GROQ_API_KEY: configurada (traducao de nomes ativa)")
            else:
                linhas.append("GROQ_API_KEY: NAO configurada (digite nomes em ingles)")

            linhas.append("")
            import os
            linhas.append(f"Modelo treinado: {'SIM' if os.path.exists(cfg.MODELO_PATH) else 'NAO'}")
            linhas.append(f"Dataset: {'SIM' if os.path.exists(cfg.DATASET_PATH) else 'NAO'}")

            texto = "\n".join(linhas)
            self.after(0, lambda: self._txt_status.insert("end", texto))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Nivel do bot
    # ------------------------------------------------------------------
    def _atualizar_nivel_label(self):
        n = nivel.obter_nivel()
        cor = "#e74c3c" if n["nivel"] < 4 else ("#f1c40f" if n["nivel"] < 7 else "#2ecc71")
        self._lbl_nivel.configure(
            text=f"Nivel: {n['nivel']}/10 ({n['win_rate']}%)",
            text_color=cor,
        )

    # ------------------------------------------------------------------
    # Carregamento do modelo na inicializacao
    # ------------------------------------------------------------------
    def _carregar_modelo(self):
        def worker():
            try:
                m, s, n, nome = modelo.treinar_modelo()
                self._modelo = m
                self._scaler = s
                self._n_amostras = n
                self._nome_modelo = nome

                if m is not None:
                    self.after(0, lambda: self._lbl_status.configure(
                        text=f"Modelo: {nome} ({n} amostras)", text_color="green"
                    ))
                else:
                    self.after(0, lambda: self._lbl_status.configure(
                        text="Modelo: apenas Poisson", text_color="yellow"
                    ))
            except Exception:
                self.after(0, lambda: self._lbl_status.configure(
                    text="Modelo: erro ao carregar", text_color="red"
                ))

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    App().mainloop()
