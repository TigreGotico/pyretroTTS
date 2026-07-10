void pht0draw (LPTTS_HANDLE_T phTTS)
{


 short dtglst = 0;
 int pseudojitter = 0;
 short keepdur = 0, keepallo = 0;
 PKSD_T pKsd_t;
 PDPH_T pDph_t;
 PDPHSETTAR_ST pDphsettar;
 short f0seg = 0, f0in = 0, phocur = 0, f0command = 0;

 pKsd_t = phTTS->pKernelShareData;
 pDph_t = phTTS->pPHThreadData;
 pDphsettar = pDph_t->pSTphsettar;
# 2404 "ph_drwt01.c"
 if (pDph_t->nf0ev <= -2)
 {
# 2416 "ph_drwt01.c"
  pDphsettar->f0beginfall = 1070 + (pDph_t->f0basefall >> 1);
  pDphsettar->f0endfall = 1070 - (pDph_t->f0basefall >> 1);

  pDphsettar->nframb = 0;




  pDphsettar->tglstp = -200;

  pDphsettar->f0las1 = pDphsettar->f0beginfall << 3;
  pDphsettar->f0las2 = pDphsettar->f0beginfall << 3;
  pDph_t->f0 = pDphsettar->f0beginfall;
  pDphsettar->tarhat = 0;

  pDphsettar->tarimp = 0;

  pDphsettar->f0a2 = pDph_t->f0_lp_filter;
  pDphsettar->f0b = 16384 - pDph_t->f0_lp_filter;
  pDphsettar->f0a1 = pDphsettar->f0a2 << 3;

  pDphsettar->newnote = pDphsettar->f0beginfall;
  pDphsettar->delnote = 0;
  pDphsettar->delcum = 0;
  pDphsettar->f0start = pDph_t->f0;
  pDphsettar->vibsw = 0;

   pDphsettar->timecos10=0; pDphsettar->timecos15=0; pDphsettar->timecosvib=0;

  pDph_t->nf0ev = -1;
 }


 if (pDph_t->nf0ev == -1)
 {

  pDphsettar->f0las1 = pDphsettar->f0beginfall << 3;
  pDphsettar->f0las2 = pDphsettar->f0beginfall << 3;
# 2466 "ph_drwt01.c"
  pDphsettar->beginfall = pDphsettar->f0beginfall;
  pDphsettar->endfall = pDphsettar->f0endfall;






  pDphsettar->nframb = 0;


  if (pDph_t->newparagsw != 0)
  {
   pDphsettar->beginfall += 120;
   pDphsettar->endfall += 70;



   pDph_t->newparagsw = 0;
  }


  pDphsettar->dtimf0 = pDph_t->f0tim[0];

  pDphsettar->np_drawt0 = -1;
  pDphsettar->npg = -1;
  pDph_t->nf0ev = 0;

  pDphsettar->nframs = 12 - (pDph_t->f0_lp_filter >> 8);





  if (pDph_t->f0mode < 4)
  {
   pDphsettar->nfram = (pDphsettar->nframs >> 1);
  }
  else
  {
   pDphsettar->nfram = 0;
  }
  pDphsettar->nframg = 0;




  pDphsettar->extrad = 0;

  pDphsettar->segdur = 0;
  pDphsettar->segdrg = 0;

  keepallo = 0;
# 2536 "ph_drwt01.c"
  pDphsettar->lastone = -1;
# 2545 "ph_drwt01.c"
  keepdur = 0;

  pDphsettar->tarhat = 0;
 }
# 2559 "ph_drwt01.c"
 while ((pDphsettar->nfram >= pDphsettar->dtimf0) &&
     ((pDph_t->nf0ev) < (pDph_t->nf0tot)))
 {

  f0command = pDph_t->f0tar[pDph_t->nf0ev];

  pDphsettar->nfram -= pDphsettar->dtimf0;
  pDphsettar->dtimf0 = pDph_t->f0tim[++(pDph_t->nf0ev)];

  if (f0command == 0)
  {
   pDphsettar->nframb = 0;
   pDphsettar->tarhat = 0;
  }

  else if (f0command >= 2000)
  {
   set_user_target (pDph_t, &f0command);
  }

  else if ((f0command & 01) == 0)

  {
   pDphsettar->tarhat += f0command;
   if (f0command < 0)
    pDphsettar->tarimp = 0;

  }
# 2631 "ph_drwt01.c"
  else
  {

   pDphsettar->tarimp = f0command + f0command;





   pDphsettar->nimp = 16 - ((pDph_t->f0_lp_filter - 1300) >> 8);

  }
# 2663 "ph_drwt01.c"
 }




 pDphsettar->tarbas = pDphsettar->beginfall - pDphsettar->nframb;

 if (pDphsettar->tarbas > pDphsettar->endfall)
  pDphsettar->nframb++;




 if (--(pDphsettar->nimp) < 0)
 {
  pDphsettar->tarimp = 0;
# 2699 "ph_drwt01.c"
 }






 if ((pDphsettar->nframs >= (pDphsettar->segdur + pDphsettar->extrad)) &&




  (pDphsettar->np_drawt0 < (pDph_t->nallotot - 1)))

 {
  pDphsettar->nframs -= pDphsettar->segdur;
  pDphsettar->segdur = pDph_t->allodurs[++(pDphsettar->np_drawt0)];
  pDphsettar->extrad = 0;
  phocur = pDph_t->allophons[pDphsettar->np_drawt0];

  if (pDphsettar->np_drawt0 < pDph_t->nallotot)
  {
   pDphsettar->phonex_drawt0 = pDph_t->allophons[pDphsettar->np_drawt0 + 1];
  }

  f0seg = us_f0segtars[phocur & 0x00FF];




  if ((pDph_t->allofeats[pDphsettar->np_drawt0] & 03) ==0)
  {
   f0seg = f0seg >> 1;
  }

  if ((phone_feature( pDph_t,pDphsettar->phonex_drawt0) & 0000002) ==0)
  {
# 2744 "ph_drwt01.c"
   pDphsettar->extrad = 2;

  }

  if ((phone_feature( pDph_t,phocur) & 0000002) ==0)
  {
   pDphsettar->tarseg1 = f0seg;
   pDphsettar->tarseg = 0;
   pDphsettar->extrad = 0;
   if ((phone_feature( pDph_t,phocur) & 0000100) !=0)
   {




    pDphsettar->extrad = 5;

   }



  }
  else
  {
   pDphsettar->tarseg = f0seg;
   pDphsettar->tarseg1 = 0;



  }
 }


 set_tglst (pDph_t);

 if (pDph_t->f0mode < 4)
 {
# 2797 "ph_drwt01.c"
                f0in = (pDphsettar->tarbas + pDphsettar->tarhat +
                                pDphsettar->tarimp + pDphsettar->tarseg);
# 2809 "ph_drwt01.c"
  pDph_t->arg1 = pDphsettar->tarseg;
  pDph_t->arg2 = 16064;
  pDphsettar->tarseg = (S16)(((S32)((S32)(pDph_t->arg1) * (S32)(pDph_t->arg2))) >> ((S32)14) );




  filter_commands (pDph_t, f0in);
# 2832 "ph_drwt01.c"
 }

 else
 {



  linear_interp (pDph_t);
 }



 dtglst = pDphsettar->nframg - pDphsettar->tglstp;
 if (dtglst <0)
  dtglst = (-dtglst);
 if (dtglst <= 7)
  pDph_t->f0prime += ((dtglst * 70) - 550);

 if (dtglst <= 5)
 {
  pDph_t->avglstop = (6 - dtglst);
 }
 else
  pDph_t->avglstop = 0;




 if (pDph_t->f0prime > 5121)
 {
  pDph_t->f0prime = 5121;
 }
 else if (pDph_t->f0prime < 500)
 {
  pDph_t->f0prime = 500;
 }


 if (pDph_t->f0mode < 4)
 {
  pDph_t->f0prime = pDph_t->f0minimum
   + (((S32)((pDph_t->f0prime - 1200))*(S32)(pDph_t->f0scalefac))>>12);





  pDphsettar->timecos15 += 43;

  if (pDphsettar->timecos15 > 4096)
   pDphsettar->timecos15 -= 4096;
  pDphsettar->timecos10 += 97;

  if (pDphsettar->timecos10 > 4096)
   pDphsettar->timecos10 -= 4096;



  pseudojitter = getcosine[pDphsettar->timecos15 >> 6]
   + getcosine[pDphsettar->timecos10 >> 6];




  pDph_t->f0prime += (pseudojitter >> 5);





  if (pDph_t->f0prime > 5121)
  {
   pDph_t->f0prime = 5121;
  }
  else if (pDph_t->f0prime < 500)
  {
   pDph_t->f0prime = 500;
  }
 }

 else if (pDph_t->f0mode == 4)
 {
  pDph_t->f0prime = (((S32)(pDph_t->f0prime)*(S32)(4190))>>12);



 }



 pDph_t->arg1 = 400;
 pDph_t->arg2 = 1000;
 pDph_t->arg3 = pDph_t->f0prime;
 pDph_t->parstochip[9]= temp = (((S32)(pDph_t->arg1) * (S32)(pDph_t->arg2)) / (S32)(pDph_t->arg3));
# 2952 "ph_drwt01.c"
 if (((pKsd_t->logflag) & 0x0020) || ((pKsd_t->debug_switch & 0x2000) && (pKsd_t->debug_switch & 0x008)))
 {
# 2964 "ph_drwt01.c"
  if (pDphsettar->np_drawt0 != pDphsettar->lastone)
  {





   if ((pDphsettar->np_drawt0 >= 0))
   {
# 2982 "ph_drwt01.c"
    dologphoneme (phTTS, pDph_t->allophons[pDphsettar->np_drawt0],
         (pDph_t->allodurs[pDphsettar->np_drawt0] * 71 / 10),
         (pDph_t->f0prime / 10));

    printf ("\n");

    if (pKsd_t->logflag & 0x0020)
    {
     if (fprintf (phTTS->pLogFile, "\n") < 0)
     {
      TextToSpeechErrorHandler (phTTS,
              5,
              0L);
     }
    }


   }



   pDphsettar->lastone = pDphsettar->np_drawt0;
  }
 }
# 3017 "ph_drwt01.c"
 pDphsettar->nfram++;
 pDphsettar->nframs++;
 pDphsettar->nframg++;


 pDph_t->parstochip[17] = pDph_t->allophons[pDphsettar->np_drawt0];
 pDph_t->parstochip[18] = pDph_t->allodurs[pDphsettar->np_drawt0];

}
# 3045 "ph_drwt01.c"
static void set_user_target (PDPH_T pDph_t, short *psF0command)
{

 short trandur = 0;
 PDPHSETTAR_ST pDphsettar = pDph_t->pSTphsettar;

 *psF0command -= 2000;




