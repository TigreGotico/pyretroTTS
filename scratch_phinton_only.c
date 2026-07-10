void phinton (LPTTS_HANDLE_T phTTS)

{

 PKSD_T pKsd_t = phTTS->pKernelShareData;
 PDPH_T pDph_t = phTTS->pPHThreadData;
 short n;
 PDPHSETTAR_ST pDphsettar = pDph_t->pSTphsettar;



 short nphon = 0, mf0 = 0;
 short pholas = 0, struclas = 0, fealas = 0;
 short struccur = 0, feacur = 0, stresscur = 0;
 short phonex = 0, strucnex = 0, feanex = 0;
 short targf0 = 0, delayf0 = 0;
 short f0fall = 0;
 short nphonx = 0;
 short cumdur = 0, phocur = 0;
 short inputscrewup = 0;







 pDphsettar->nrises_sofar = 0;
 pDphsettar->hatsize = 0;
 pDphsettar->hat_loc_re_baseline = 0;


 inputscrewup = 0;
 cumdur = 0;

 pDph_t->had_hatbegin=0;
 pDph_t->had_hatend=0;
 pDph_t->nf0tot = 0;
 pholas = 0x01E00;
 fealas = (all_featb[(0x01E00)>>8][(0x01E00)&0x00ff]);
 struclas = 0;
 mf0 = 0;





 for (nphon = 0; nphon < pDph_t->nallotot; nphon++)
 {

  if (nphon > 0)
  {
   pholas = pDph_t->allophons[nphon - 1];
   struclas = pDph_t->allofeats[nphon - 1];
   fealas = (all_featb[(pholas)>>8][(pholas)&0x00ff]);
  }
  phocur = pDph_t->allophons[nphon];
  struccur = pDph_t->allofeats[nphon];
  stresscur = struccur & 03;
  feacur = (all_featb[(phocur)>>8][(phocur)&0x00ff]);
  if (nphon < (pDph_t->nallotot - 1))
  {
   phonex = pDph_t->allophons[nphon + 1];
   strucnex = pDph_t->allofeats[nphon + 1];
   feanex = (all_featb[(phonex)>>8][(phonex)&0x00ff]);
  }
# 1409 "ph_inton0.c"
  if ((pDph_t->f0mode == 5)
   || (pDph_t->f0mode == 4))
  {

   if (pDph_t->user_f0[nphon] != 0)
   {
    make_f0_command (pDph_t, 0, (2000 + pDph_t->user_f0[nphon]),
         0,0, &cumdur);
   }
   goto skiprules;
  }
# 1428 "ph_inton0.c"
  if((struccur & 01000) !=0)
   pDph_t->had_hatbegin= 1;
  if((struccur & 02000) !=0)
   pDph_t->had_hatend= 1;

  if ((pDph_t->f0mode == 1) || (pDph_t->f0mode == 3))
  {

   if ((feacur & 0000001) !=0)
   {




    if (pDph_t->had_hatbegin)
    {
     pDph_t->had_hatbegin=0;
     delayf0 +=1;




     if (pDph_t->f0mode == 1)

     {
      pDphsettar->hatsize = pDph_t->size_hat_rise;




      if (pDph_t->cbsymbol)
      {

       pDphsettar->hatsize >>= 1;




      }
      pDphsettar->hatsize &= 037776;
      pDphsettar->hatsize |= 02;



      delayf0 = 0;





      if ((struccur & 02000) !=0)
      {
       delayf0 = -13;
      }

      make_f0_command (pDph_t, 1, pDphsettar->hatsize, delayf0,0, &cumdur);
     }
     else if (pDph_t->f0mode == 3)
     {
      pDphsettar->hatsize = ((pDph_t->user_f0[mf0] - 200) * 10) + 2;
      if ((pDphsettar->hatsize >= 2000) || (pDphsettar->hatsize <= 0)
       || (inputscrewup == 1))
      {
       pDphsettar->hatsize = 2;
       logscrewup (phocur, &inputscrewup);
      }
      delayf0 = mstofr (pDph_t->user_offset[mf0]);
      mf0++;

      make_f0_command (pDph_t, 1, pDphsettar->hatsize, delayf0,0, &cumdur);
     }

     pDphsettar->hat_loc_re_baseline += pDphsettar->hatsize;
    }
# 1516 "ph_inton0.c"
                targf0=0;

    if ((stresscur & 01) !=0)




    {


     targf0 = us_f0_stress_level[stresscur]
      + us_f0_phrase_position[pDphsettar->nrises_sofar];

     if (pDph_t->cbsymbol)
     {

      targf0 >>= 1;
# 1542 "ph_inton0.c"
     }
# 1554 "ph_inton0.c"
     delayf0 = pDph_t->allodurs[nphon] >> 2;
# 1563 "ph_inton0.c"
     if (((struccur & 02000) !=0)
      || ((struccur & 0400) !=0))
     {
      delayf0 = -9;





     }

     if (stresscur == 03)
     {

      delayf0 = 0;




     }

     if (pDph_t->f0mode == 3)
     {
      targf0 = ((pDph_t->user_f0[mf0] - 1000) * 10) + 1;
      if ((targf0 >= 2000) || (targf0 <= 0)
       || (inputscrewup == 1))
      {
       targf0 = 1;
       logscrewup (phocur, &inputscrewup);
      }
      delayf0 = mstofr (pDph_t->user_offset[mf0]);
      mf0++;
     }


     pDph_t->arg1 = pDph_t->scale_str_rise;
     if ((stresscur == 03) && (pDph_t->arg1 < 16))
     {
      pDph_t->arg1 = 16;
     }
     pDph_t->arg2 = targf0;
     pDph_t->arg3 = 32;
     targf0 = (((S32)(pDph_t->arg1) * (S32)(pDph_t->arg2)) / (S32)(pDph_t->arg3));
     targf0 |= 01;


     make_f0_command (pDph_t, 2, targf0, delayf0,0, &cumdur);


     if (pDphsettar->nrises_sofar < 4)
      pDphsettar->nrises_sofar++;
    }






    if ( pDph_t->had_hatend)
    {
      pDph_t->had_hatend=0;



     if (pDph_t->f0mode == 1)
     {




      f0fall = 180;

      delayf0 = pDph_t->allodurs[nphon] - 25;

      if (delayf0 < 4)
       delayf0 = 4;


      if ((struccur & 0740) == 0340)
      {
       f0fall = 120;
      }

      if ((struccur & 0740) == 0240)
      {
       f0fall = 0;
      }

      if ((struccur & 0740) < 0240)
      {


       for (nphonx = nphon + 1; nphonx < pDph_t->nallotot; nphonx++)
       {
        if ((pDph_t->allofeats[nphonx] & 01000) !=0)
        {

         f0fall = 0;
         goto bfound;
        }
        if (((all_featb[(pDph_t->allophons[nphonx])>>8][(pDph_t->allophons[nphonx])&0x00ff]) & 0000001) !=0)
        {

         if ((pDph_t->allofeats[nphonx] & 03) ==0)
         {


          delayf0 = pDph_t->allodurs[nphon] - 8;
         }
         if ((pDph_t->allofeats[nphonx] & 0740) == 0240)
         {

          f0fall = 0;
          goto bfound;
         }
         if ((pDph_t->allofeats[nphonx] & 0740) > 0240)
         {

          f0fall = 150;
          goto bfound;
         }

        }
       }
      }




       bfound:if ((struccur & 0740) == 0440)
      {
       f0fall = 80;
      }



        f0fall = (((S32)(f0fall)*(S32)(pDph_t->assertiveness))>>12);

      if (pDph_t->cbsymbol)
      {
       f0fall = f0fall >> 1;
      }
      f0fall &= 037776;

      f0fall += pDphsettar->hatsize;
     }
# 1776 "ph_inton0.c"
     else if (pDph_t->f0mode == 3)
     {
      f0fall = ((pDph_t->user_f0[mf0] - 400) * 10) + 2;
      if ((f0fall >= 2000) || (f0fall <= 0)
       || (inputscrewup == 1))
      {
       f0fall = 2;
       logscrewup (phocur, &inputscrewup);
      }
      delayf0 = mstofr (pDph_t->user_offset[mf0]);
      mf0++;
     }

     make_f0_command (pDph_t, 3, -f0fall, delayf0,0, &cumdur);
     pDphsettar->hat_loc_re_baseline -= f0fall;
    }
# 1806 "ph_inton0.c"
    if (((struccur & 0740) == 0340)
     || ((struccur & 0740) == 0440))
    {

     delayf0 = pDph_t->allodurs[nphon] - 13;
# 1821 "ph_inton0.c"
     if ((struccur & 0740) == 0440)
     {


      make_f0_command (pDph_t, 4, 181, delayf0,0, &cumdur);
      make_f0_command (pDph_t, 4, 251, pDph_t->allodurs[nphon],0, &cumdur);





     }
     else
     {


      delayf0 += 3;
      make_f0_command (pDph_t, 4, 71, delayf0,0, &cumdur);
      make_f0_command (pDph_t, 4, 101, pDph_t->allodurs[nphon],0, &cumdur);





     }
    }
   }






   if ((feacur & 0000001) !=0)
   {
    if (((stresscur & 01) ==0)
     || ((struccur & 02000) ==0))
    {
# 1867 "ph_inton0.c"
      if (((struccur & 0740) == 0400)
       || ((struccur & 0740) == 0500))
      {
       targf0 = -60;




       targf0 = (((S32)(targf0)*(S32)(pDph_t->assertiveness))>>12);
       targf0 |= 01;

       make_f0_command (pDph_t, 5, targf0, pDph_t->allodurs[nphon] - 16,0, &cumdur);
      }





      delayf0 = pDph_t->allodurs[nphon] - 13;
      if ((struccur & 0740) == 0440)
      {


       make_f0_command (pDph_t, 6, 181, delayf0,0, &cumdur);
       make_f0_command (pDph_t, 6, 251, pDph_t->allodurs[nphon],0, &cumdur);




      }
      if ((struccur & 0740) == 0340)
      {


       delayf0 += 3;
       make_f0_command (pDph_t, 6, 71, delayf0,0, &cumdur);
       make_f0_command (pDph_t, 6, 101, pDph_t->allodurs[nphon],0, &cumdur);




      }




    }
   }



   if (phocur == 0x01E00)
   {


    if ((pDphsettar->hat_loc_re_baseline != 0) && (pDph_t->nf0tot > 0))
    {





      make_f0_command (pDph_t, 7, -(pDphsettar->hat_loc_re_baseline),0, 0, &cumdur);
     pDphsettar->hat_loc_re_baseline = 0;
    }

    if (nphon > 0)
     pDphsettar->nrises_sofar = 1;
# 1949 "ph_inton0.c"
    if ((struclas & 0400) !=0)
    {
     make_f0_command (pDph_t, 8, 0, 0, 0, &cumdur);
     pDphsettar->hat_loc_re_baseline = 0;

     pDphsettar->nrises_sofar = 0;
    }
   }

  }

   skiprules:


  cumdur += pDph_t->allodurs[nphon];






  if ((phonex == 0x01E00)
   && (((phocur >= (( 0x1E<<8) |45)) && (phocur <= (( 0x1E<<8) |50)))
                                                  )

   && (pDph_t->nallotot < 300))
  {
   for (n = pDph_t->nallotot; n > nphon; n--)
   {
    pDph_t->allophons[n] = pDph_t->allophons[n - 1];
    pDph_t->allofeats[n] = pDph_t->allofeats[n - 1];
    pDph_t->allodurs[n] = pDph_t->allodurs[n - 1];
    pDph_t->user_f0[n] = pDph_t->user_f0[n - 1];
   }
   pDph_t->allophons[nphon + 1] = (( 0x1E<<8) |17);
   if ((pholas < (( 0x1E<<8) |5))
    || ((phocur >= (( 0x1E<<8) |47)) && (phocur <= (( 0x1E<<8) |48))))
   {
    pDph_t->allophons[nphon + 1] = (( 0x1E<<8) |18);
   }
   pDph_t->allodurs[nphon + 1] = 4;
   cumdur += 4;
   pDph_t->allofeats[nphon + 1] = pDph_t->allofeats[nphon] | 004000;
   pDph_t->nallotot++;
   nphon++;
  }
# 2027 "ph_inton0.c"
 }
}
# 2049 "ph_inton0.c"
static void make_f0_command (PDPH_T pDph_t, short rulenumber, short tar, short delay,
          short length, short *psCumdur)


{
 PKSD_T pKsd_t = pDph_t->phTTS->pKernelShareData;
# 2063 "ph_inton0.c"
 if (((pKsd_t->debug_switch & 0x2000) && (pKsd_t->debug_switch & 0x010)))
  printf("rule %d tar %d delay %d length %d  \n", rulenumber, tar, delay, length);

 if ((delay + *psCumdur) < 0)
 {
  delay = -(*psCumdur);
 }


 pDph_t->f0tim[pDph_t->nf0tot] = *psCumdur + delay;
 pDph_t->f0tar[pDph_t->nf0tot] = tar;


 *psCumdur = (-delay);


 if (pDph_t->nf0tot < 300 - 1)
 {
  pDph_t->nf0tot++;
 }

}
# 2100 "ph_inton0.c"
void logscrewup (short phocur, short *inputscrewup)
{

 *inputscrewup = 1;
}
# 49 "ph_inton.c" 2
